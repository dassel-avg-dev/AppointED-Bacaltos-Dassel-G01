import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from scheduling import services
from scheduling.models import Appointment, AppointmentType, Status, TimeSlot
from scheduling.services import BusinessRuleError


def make_users():
    f = User.objects.create_user("f@x.com", "pw", full_name="Fac", role="FACULTY")
    f2 = User.objects.create_user("f2@x.com", "pw", full_name="Fac2", role="FACULTY")
    s = User.objects.create_user("s@x.com", "pw", full_name="Stu", role="STUDENT")
    s2 = User.objects.create_user("s2@x.com", "pw", full_name="Stu2", role="STUDENT")
    return f, f2, s, s2


def future_slot(faculty, days=2, hour=9, length=1):
    d = (timezone.localtime() + datetime.timedelta(days=days)).date()
    return TimeSlot.objects.create(
        faculty=faculty, slot_date=d, start_time=datetime.time(hour), end_time=datetime.time(hour + length)
    )


def past_slot(faculty):
    """A slot that already ended (yesterday)."""
    d = (timezone.localtime() - datetime.timedelta(days=1)).date()
    return TimeSlot.objects.create(
        faculty=faculty, slot_date=d, start_time=datetime.time(9), end_time=datetime.time(10)
    )


class ModelConstraintTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.t = AppointmentType.objects.first()

    def test_seeded_types(self):
        self.assertEqual(AppointmentType.objects.count(), 4)

    def test_end_after_start(self):  # BR-03
        with self.assertRaises(IntegrityError), transaction.atomic():
            TimeSlot.objects.create(faculty=self.f, slot_date=datetime.date(2030, 1, 1),
                                    start_time=datetime.time(10), end_time=datetime.time(9))

    def test_unique_faculty_date_start(self):  # BR-04
        future_slot(self.f)
        with self.assertRaises(IntegrityError), transaction.atomic():
            future_slot(self.f, length=2)

    def test_one_active_per_slot_and_rebook_after_cancel(self):  # BR-07
        slot = future_slot(self.f)
        a = Appointment.objects.create(student=self.s, slot=slot, type=self.t, purpose="x")
        self.assertEqual(a.status, "PENDING")  # BR-09
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(student=self.s2, slot=slot, type=self.t, purpose="y")
        a.status = "CANCELLED"
        a.save()
        Appointment.objects.create(student=self.s2, slot=slot, type=self.t, purpose="y")

    def test_bad_status(self):  # BR-08
        slot = future_slot(self.f)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(student=self.s, slot=slot, type=self.t, purpose="x", status="BOGUS")

    def test_purpose_required(self):  # BR-14
        slot = future_slot(self.f)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(student=self.s, slot=slot, type=self.t, purpose="")

    def test_slot_with_appointment_not_deletable(self):  # BR-13
        slot = future_slot(self.f)
        Appointment.objects.create(student=self.s, slot=slot, type=self.t, purpose="x")
        with self.assertRaises(BusinessRuleError):
            services.delete_slot(self.f, slot)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            slot.delete()


class ServiceTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.t = AppointmentType.objects.first()

    def _date(self, days=2):
        return (timezone.localtime() + datetime.timedelta(days=days)).date()

    def test_only_faculty_create_slots(self):  # BR-05
        with self.assertRaises(BusinessRuleError):
            services.create_slot(self.s, self._date(), datetime.time(9), datetime.time(10))

    def test_no_past_slots(self):  # X1
        with self.assertRaises(BusinessRuleError):
            services.create_slot(self.f, self._date(-1), datetime.time(9), datetime.time(10))

    def test_overlap_rejected(self):  # X2
        services.create_slot(self.f, self._date(), datetime.time(9), datetime.time(11))
        with self.assertRaises(BusinessRuleError):
            services.create_slot(self.f, self._date(), datetime.time(10), datetime.time(12))
        services.create_slot(self.f, self._date(), datetime.time(11), datetime.time(12))  # adjacent OK
        services.create_slot(self.f2, self._date(), datetime.time(10), datetime.time(12))  # other faculty OK

    def test_only_students_book(self):  # BR-06
        slot = future_slot(self.f)
        with self.assertRaises(BusinessRuleError):
            services.book_appointment(self.f2, slot, self.t, "x")

    def test_cannot_book_started_slot(self):  # X3
        with self.assertRaises(BusinessRuleError):
            services.book_appointment(self.s, past_slot(self.f), self.t, "x")

    def test_book_logs_and_blocks_second(self):
        slot = future_slot(self.f)
        a = services.book_appointment(self.s, slot, self.t, "help")
        self.assertEqual(a.status, Status.PENDING)
        log = a.logs.get()
        self.assertEqual((log.old_status, log.new_status, log.changed_by), (None, "PENDING", self.s))
        with self.assertRaises(BusinessRuleError):
            services.book_appointment(self.s2, slot, self.t, "me too")

    def test_purpose_required_service(self):
        with self.assertRaises(BusinessRuleError):
            services.book_appointment(self.s, future_slot(self.f), self.t, "   ")

    def _appt(self, slot=None):
        if slot is None:
            self._hour = getattr(self, "_hour", 7) + 1  # unique slot per call (BR-04)
            slot = future_slot(self.f, hour=self._hour)
        return services.book_appointment(self.s, slot, self.t, "x")

    def test_only_owner_faculty_approves(self):  # BR-10
        a = self._appt()
        with self.assertRaises(BusinessRuleError):
            services.change_status(a, Status.APPROVED, self.f2)
        with self.assertRaises(BusinessRuleError):
            services.change_status(a, Status.APPROVED, self.s)
        services.change_status(a, Status.APPROVED, self.f)
        self.assertEqual(a.logs.count(), 2)

    def test_student_cancel_only_while_pending(self):  # BR-12
        a = self._appt()
        b = self._appt()
        services.change_status(a, Status.CANCELLED, self.s)
        services.change_status(b, Status.APPROVED, self.f)
        with self.assertRaises(BusinessRuleError):
            services.change_status(b, Status.CANCELLED, self.s)

    def test_other_student_cannot_cancel(self):
        a = self._appt()
        with self.assertRaises(BusinessRuleError):
            services.change_status(a, Status.CANCELLED, self.s2)

    def test_faculty_cancel_approved(self):  # X4
        a = self._appt()
        services.change_status(a, Status.APPROVED, self.f)
        services.change_status(a, Status.CANCELLED, self.f)

    def test_complete_requires_approved_and_ended(self):  # BR-11, X5
        a = self._appt()
        with self.assertRaises(BusinessRuleError):
            services.change_status(a, Status.COMPLETED, self.f)  # pending
        services.change_status(a, Status.APPROVED, self.f)
        with self.assertRaises(BusinessRuleError):
            services.change_status(a, Status.COMPLETED, self.f)  # not ended

    def test_complete_after_slot_end(self):
        slot = past_slot(self.f)
        a = Appointment.objects.create(student=self.s, slot=slot, type=self.t, purpose="x",
                                       status=Status.APPROVED)
        services.change_status(a, Status.COMPLETED, self.f)
        a.refresh_from_db()
        self.assertEqual(a.status, Status.COMPLETED)

    def test_terminal_states(self):
        a = self._appt()
        services.change_status(a, Status.CANCELLED, self.s)
        for target in (Status.APPROVED, Status.PENDING, Status.COMPLETED):
            with self.assertRaises(BusinessRuleError):
                services.change_status(a, target, self.f)

    def test_cancelled_slot_can_be_rebooked(self):
        slot = future_slot(self.f)
        a = services.book_appointment(self.s, slot, self.t, "x")
        services.change_status(a, Status.CANCELLED, self.s)
        services.book_appointment(self.s2, slot, self.t, "y")

    def test_update_slot_success_and_self_overlap(self):
        slot = services.create_slot(self.f, self._date(), datetime.time(9), datetime.time(11))
        updated = services.update_slot(self.f, slot, self._date(), datetime.time(9, 30), datetime.time(11))
        self.assertEqual(updated.start_time, datetime.time(9, 30))
        self.assertEqual(updated.end_time, datetime.time(11))

    def test_update_slot_rejections(self):
        slot = services.create_slot(self.f, self._date(), datetime.time(9), datetime.time(10))
        services.create_slot(self.f, self._date(), datetime.time(11), datetime.time(12))
        with self.assertRaises(BusinessRuleError):
            services.update_slot(self.f2, slot, self._date(), datetime.time(9), datetime.time(10))
        with self.assertRaises(BusinessRuleError):
            services.update_slot(self.f, slot, self._date(-1), datetime.time(9), datetime.time(10))
        with self.assertRaises(BusinessRuleError):
            services.update_slot(self.f, slot, self._date(), datetime.time(10), datetime.time(9))
        with self.assertRaises(BusinessRuleError):
            services.update_slot(self.f, slot, self._date(), datetime.time(10, 30), datetime.time(11, 30))
        services.book_appointment(self.s, slot, self.t, "x")
        with self.assertRaises(BusinessRuleError):
            services.update_slot(self.f, slot, self._date(), datetime.time(8), datetime.time(9))
