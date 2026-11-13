import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from accounts.models import Department, User
from scheduling.models import Appointment, AppointmentLog, AppointmentType, Status, TimeSlot

PASSWORD = "demo12345"

ADMIN = ("admin@demo.test", "Demo Admin")
FACULTY = [
    ("santos@demo.test", "Prof. Maria Santos", "College of Computer Studies"),
    ("reyes@demo.test", "Prof. Jose Reyes", "College of Engineering"),
    ("cruz@demo.test", "Prof. Ana Cruz", "College of Business"),
]
STUDENTS = [
    ("student1@demo.test", "Juan Dela Cruz", "College of Computer Studies"),
    ("student2@demo.test", "Maria Clara", "College of Engineering"),
    ("student3@demo.test", "Pedro Penduko", "College of Business"),
]


class Command(BaseCommand):
    help = (
        "Create demo accounts, slots and appointments for local testing. "
        "Idempotent. Refuses to run on non-SQLite databases unless --force."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Allow on non-SQLite databases.")

    def handle(self, *args, **opts):
        if connection.vendor != "sqlite" and not opts["force"]:
            raise CommandError(
                f"Database is {connection.vendor}, not SQLite. Demo data is for local testing; "
                "use --force if you really want it here."
            )

        self._users()
        self._data()
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready. All demo accounts use password '{PASSWORD}'. See context/sample-credentials.md."
        ))

    # ---- users ----
    def _user(self, email, name, role, dept_name=None):
        dept = Department.objects.filter(name=dept_name).first() if dept_name else None
        user, _ = User.objects.get_or_create(
            email=email, defaults={"full_name": name, "role": role, "department": dept}
        )
        user.full_name, user.role, user.department, user.is_active = name, role, dept, True
        user.set_password(PASSWORD)
        user.save()
        return user

    def _users(self):
        self.admin = self._user(ADMIN[0], ADMIN[1], "ADMIN")
        self.fac = {e: self._user(e, n, "FACULTY", d) for e, n, d in FACULTY}
        self.stu = {e: self._user(e, n, "STUDENT", d) for e, n, d in STUDENTS}

    # ---- slots and appointments ----
    def _slot(self, fac, day_offset, hour, length=1):
        slot, _ = TimeSlot.objects.get_or_create(
            faculty=fac,
            slot_date=timezone.localdate() + datetime.timedelta(days=day_offset),
            start_time=datetime.time(hour),
            defaults={"end_time": datetime.time(hour + length)},
        )
        return slot

    def _appt(self, slot, student, type_name, purpose, final, fac):
        """Create an appointment that walked PENDING -> ... -> final, with a full log."""
        if slot.appointments.exists():
            return
        atype = AppointmentType.objects.get(type_name=type_name)
        appt = Appointment.objects.create(student=student, slot=slot, type=atype, purpose=purpose)
        AppointmentLog.objects.create(appointment=appt, changed_by=student, new_status=Status.PENDING)
        path = {
            Status.PENDING: [],
            Status.APPROVED: [(Status.APPROVED, fac)],
            Status.COMPLETED: [(Status.APPROVED, fac), (Status.COMPLETED, fac)],
            Status.CANCELLED: [(Status.CANCELLED, student)],
        }[final]
        old = Status.PENDING
        for new, actor in path:
            appt.status = new
            appt.save()
            AppointmentLog.objects.create(
                appointment=appt, changed_by=actor, old_status=old, new_status=new
            )
            old = new

    def _data(self):
        santos, reyes, _cruz = (self.fac[e] for e, _, _ in FACULTY)
        s1, s2, s3 = (self.stu[e] for e, _, _ in STUDENTS)

        # Santos: pending, approved, cancelled-and-reopened, open slots, plus past ones
        self._appt(self._slot(santos, 1, 9), s1, "Consultation", "Thesis topic consultation", Status.PENDING, santos)
        self._appt(self._slot(santos, 1, 10), s2, "Advising", "Course advising for next term", Status.APPROVED, santos)
        self._appt(self._slot(santos, 2, 9), s3, "Clearance", "Clearance signature", Status.CANCELLED, santos)
        self._slot(santos, 2, 14)
        self._slot(santos, 3, 9)
        # Past slots: the approved one lets faculty try "Complete"
        self._appt(self._slot(santos, -1, 9), s1, "Consultation", "Follow-up on thesis outline", Status.APPROVED, santos)
        self._appt(self._slot(santos, -2, 13), s3, "Document Request", "Request for course syllabus", Status.COMPLETED, santos)

        # Reyes: one pending request and open slots
        self._appt(self._slot(reyes, 1, 13), s2, "Consultation", "Design project feedback", Status.PENDING, reyes)
        self._slot(reyes, 2, 10)
        self._slot(reyes, 4, 15)

        # Cruz: no slots at all (shows the empty state)
