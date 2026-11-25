import datetime
from unittest.mock import patch

from django.db import IntegrityError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from config.views import server_error
from scheduling import services
from scheduling.models import Appointment, AppointmentType, Status, TimeSlot
from scheduling.services import BusinessRuleError

from .test_services import future_slot, make_users, past_slot


class CoreHardeningTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.admin = User.objects.create_superuser("admin@x.com", "pw", full_name="Admin")
        self.t = AppointmentType.objects.first()

    def _future_date(self, days=2):
        return (timezone.localtime() + datetime.timedelta(days=days)).date()

    # ---- 1. Authentication required on every core view ----
    def test_all_core_views_require_login(self):
        slot = future_slot(self.f)
        appt = services.book_appointment(self.s, slot, self.t, "Need advice")
        urls = [
            ("get", reverse("scheduling:dashboard")),
            ("get", reverse("scheduling:slot_list")),
            ("get", reverse("scheduling:slot_create")),
            ("get", reverse("scheduling:slot_edit", args=[slot.pk])),
            ("post", reverse("scheduling:slot_delete", args=[slot.pk])),
            ("get", reverse("scheduling:faculty_directory")),
            ("get", reverse("scheduling:faculty_slots", args=[self.f.pk])),
            ("get", reverse("scheduling:book", args=[slot.pk])),
            ("get", reverse("scheduling:appointment_list")),
            ("get", reverse("scheduling:appointment_detail", args=[appt.pk])),
            ("post", reverse("scheduling:appointment_status", args=[appt.pk])),
        ]
        for method, url in urls:
            resp = getattr(self.client, method)(url)
            self.assertEqual(resp.status_code, 302, f"{method.upper()} {url}")
            self.assertIn(reverse("accounts:login"), resp.url)

    # ---- 2. Valid & invalid inputs on TimeSlot forms/views ----
    def test_slot_create_valid_input(self):
        self.client.force_login(self.f)
        d = self._future_date(3)
        resp = self.client.post(
            reverse("scheduling:slot_create"),
            {"slot_date": d, "start_time": "09:00", "end_time": "10:00"},
            follow=True,
        )
        self.assertRedirects(resp, reverse("scheduling:slot_list"))
        self.assertContains(resp, "Time slot added.")
        self.assertEqual(self.f.time_slots.count(), 1)

    def test_slot_create_invalid_inputs_rejected(self):
        self.client.force_login(self.f)
        future_slot(self.f, days=2, hour=9, length=2)
        d_future = self._future_date(2)
        d_past = self._future_date(-1)

        invalid_payloads = [
            ({"slot_date": d_future, "start_time": "14:00", "end_time": "13:00"}, "End time must be later than start time."),
            ({"slot_date": d_past, "start_time": "09:00", "end_time": "10:00"}, "Time slots cannot be scheduled in the past."),
            ({"slot_date": d_future, "start_time": "10:00", "end_time": "12:00"}, "This slot overlaps one of your existing slots."),
        ]
        for payload, expected_err in invalid_payloads:
            resp = self.client.post(reverse("scheduling:slot_create"), payload)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, expected_err)
        self.assertEqual(self.f.time_slots.count(), 1)

    def test_slot_edit_blocks_past_and_booked_slots(self):
        past = past_slot(self.f)
        booked = future_slot(self.f, days=3, hour=9)
        services.book_appointment(self.s, booked, self.t, "Thesis review")
        self.client.force_login(self.f)

        for target, msg in (
            (past, "Past time slots cannot be edited."),
            (booked, "A slot that has appointments cannot be edited."),
        ):
            url = reverse("scheduling:slot_edit", args=[target.pk])
            r_get = self.client.get(url, follow=True)
            self.assertRedirects(r_get, reverse("scheduling:slot_list"))
            self.assertContains(r_get, msg)
            r_post = self.client.post(
                url,
                {"slot_date": self._future_date(5), "start_time": "15:00", "end_time": "16:00"},
                follow=True,
            )
            self.assertRedirects(r_post, reverse("scheduling:slot_list"))
            self.assertContains(r_post, msg)

    def test_slot_delete_post_only_and_rejects_booked(self):
        slot = future_slot(self.f)
        services.book_appointment(self.s, slot, self.t, "Advising")
        self.client.force_login(self.f)
        url = reverse("scheduling:slot_delete", args=[slot.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url, follow=True)
        self.assertRedirects(r, reverse("scheduling:slot_list"))
        self.assertContains(r, "A slot that has appointments cannot be deleted.")
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    # ---- 3. Role checks & cross-user isolation ----
    def test_role_enforcement_on_core_views(self):
        slot = future_slot(self.f)
        self.client.force_login(self.s)
        for method, url in (
            ("get", reverse("scheduling:slot_list")),
            ("get", reverse("scheduling:slot_create")),
            ("get", reverse("scheduling:slot_edit", args=[slot.pk])),
            ("post", reverse("scheduling:slot_delete", args=[slot.pk])),
        ):
            self.assertEqual(getattr(self.client, method)(url).status_code, 403)

        self.client.force_login(self.f)
        for url in (
            reverse("scheduling:faculty_directory"),
            reverse("scheduling:faculty_slots", args=[self.f.pk]),
            reverse("scheduling:book", args=[slot.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("scheduling:slot_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("scheduling:faculty_directory")).status_code, 403)

    def test_cross_user_slot_edit_and_delete_blocked(self):
        slot = future_slot(self.f)
        self.client.force_login(self.f2)
        self.assertEqual(self.client.get(reverse("scheduling:slot_edit", args=[slot.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("scheduling:slot_edit", args=[slot.pk]),
                {"slot_date": self._future_date(4), "start_time": "10:00", "end_time": "11:00"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.post(reverse("scheduling:slot_delete", args=[slot.pk])).status_code, 404)
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    # ---- 4. Booking validation & availability guards ----
    def test_book_valid_and_invalid_inputs(self):
        slot = future_slot(self.f)
        url = reverse("scheduling:book", args=[slot.pk])
        self.client.force_login(self.s)

        # Blank/whitespace purpose rejected server-side
        r_blank = self.client.post(url, {"type": self.t.pk, "purpose": "   "})
        self.assertEqual(r_blank.status_code, 200)
        self.assertFalse(Appointment.objects.filter(slot=slot).exists())

        # Over-length purpose (> 255 chars) rejected server-side
        r_long = self.client.post(url, {"type": self.t.pk, "purpose": "a" * 256})
        self.assertEqual(r_long.status_code, 200)
        self.assertFalse(Appointment.objects.filter(slot=slot).exists())

        # Valid booking succeeds and redirects
        r_ok = self.client.post(url, {"type": self.t.pk, "purpose": "Discuss capstone scope"}, follow=True)
        appt = Appointment.objects.get(slot=slot)
        self.assertRedirects(r_ok, reverse("scheduling:appointment_detail", args=[appt.pk]))
        self.assertContains(r_ok, "Appointment requested.")
        self.assertEqual(appt.status, Status.PENDING)

    def test_book_blocks_unavailable_past_and_inactive_faculty_slots(self):
        booked_slot = future_slot(self.f, days=2, hour=9)
        services.book_appointment(self.s, booked_slot, self.t, "First")
        past = past_slot(self.f)
        inactive_fac = User.objects.create_user(
            "inactive@x.com", "pw", full_name="Inactive Fac", role="FACULTY", is_active=False
        )
        inactive_slot = future_slot(inactive_fac, days=2, hour=11)

        self.client.force_login(self.s2)
        for target, expected_msg in (
            (booked_slot, "This slot is already booked."),
            (past, "This slot has already started or passed."),
        ):
            url = reverse("scheduling:book", args=[target.pk])
            r_get = self.client.get(url, follow=True)
            self.assertRedirects(r_get, reverse("scheduling:faculty_slots", args=[self.f.pk]))
            self.assertContains(r_get, expected_msg)
            r_post = self.client.post(url, {"type": self.t.pk, "purpose": "Late"}, follow=True)
            self.assertRedirects(r_post, reverse("scheduling:faculty_slots", args=[self.f.pk]))
            self.assertContains(r_post, expected_msg)

        self.assertEqual(self.client.get(reverse("scheduling:book", args=[inactive_slot.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("scheduling:faculty_slots", args=[self.s.pk])).status_code, 404)

    def test_cross_user_appointment_access_and_disallowed_student_action(self):
        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "Topic check")
        for other in (self.s2, self.f2, self.admin):
            self.client.force_login(other)
            self.assertEqual(self.client.get(reverse("scheduling:appointment_detail", args=[appt.pk])).status_code, 404)
            self.assertEqual(
                self.client.post(reverse("scheduling:appointment_status", args=[appt.pk]), {"status": Status.CANCELLED}).status_code,
                404,
            )

        # Student cannot approve their own appointment
        self.client.force_login(self.s)
        r = self.client.post(
            reverse("scheduling:appointment_status", args=[appt.pk]),
            {"status": Status.APPROVED},
            follow=True,
        )
        self.assertContains(r, "You are not allowed to make this change.")
        appt.refresh_from_db()
        self.assertEqual(appt.status, Status.PENDING)

    # ---- 5. Non-existent IDs & custom 404 / 500 error pages ----
    def test_nonexistent_ids_and_invalid_status_return_404(self):
        self.client.force_login(self.f)
        self.assertEqual(self.client.get(reverse("scheduling:slot_edit", args=[999999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("scheduling:slot_delete", args=[999999])).status_code, 404)
        self.assertEqual(self.client.get(reverse("scheduling:appointment_detail", args=[999999])).status_code, 404)

        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "Check")
        self.assertEqual(
            self.client.post(reverse("scheduling:appointment_status", args=[appt.pk]), {"status": "BOGUS"}).status_code,
            404,
        )

        self.client.force_login(self.s)
        self.assertEqual(self.client.get(reverse("scheduling:faculty_slots", args=[999999])).status_code, 404)
        self.assertEqual(self.client.get(reverse("scheduling:book", args=[999999])).status_code, 404)

    @override_settings(DEBUG=False)
    def test_custom_404_and_500_handlers(self):
        self.client.force_login(self.s)
        r404 = self.client.get("/this-route-does-not-exist-999/")
        self.assertEqual(r404.status_code, 404)
        self.assertContains(r404, "404 · Not found", status_code=404)

        req = RequestFactory().get("/")
        r500 = server_error(req)
        self.assertEqual(r500.status_code, 500)
        self.assertIn(b"500", r500.content)

    # ---- 6. CSRF presence, query bounds & atomic error handling ----
    def test_csrf_tokens_present_on_post_forms(self):
        slot = future_slot(self.f)
        self.client.force_login(self.f)
        for url in (reverse("scheduling:slot_create"), reverse("scheduling:slot_list")):
            self.assertContains(self.client.get(url), "csrfmiddlewaretoken")
        self.client.force_login(self.s)
        self.assertContains(self.client.get(reverse("scheduling:book", args=[slot.pk])), "csrfmiddlewaretoken")

    def test_faculty_slots_and_directory_bounded_queries(self):
        for h in range(8, 15):
            slot = future_slot(self.f, days=3, hour=h)
            if h % 2 == 0:
                services.book_appointment(self.s, slot, self.t, f"Booked {h}")
        self.client.force_login(self.s)
        with self.assertNumQueries(6):
            r_dir = self.client.get(reverse("scheduling:faculty_directory"))
            self.assertEqual(r_dir.status_code, 200)
        with self.assertNumQueries(5):
            r_slots = self.client.get(reverse("scheduling:faculty_slots", args=[self.f.pk]))
            self.assertEqual(r_slots.status_code, 200)

    def test_service_slot_integrity_error_raises_business_rule_error(self):
        with patch.object(TimeSlot, "save", side_effect=IntegrityError("duplicate")):
            with self.assertRaises(BusinessRuleError):
                services.create_slot(self.f, self._future_date(5), datetime.time(9, 0), datetime.time(10, 0))
