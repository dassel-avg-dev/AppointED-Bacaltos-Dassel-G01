import datetime

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from scheduling import services
from scheduling.models import AppointmentType, Status, TimeSlot
from scheduling.templatetags.ui import friendly_day, initials, slot_when, status_badge

from .test_services import future_slot, make_users


class UIPolishTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.t = AppointmentType.objects.first()

    # ---- Theme cookie toggle ----
    def test_theme_default_light_and_toggle_dark(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertNotContains(r, 'class="dark"')
        r = self.client.post(reverse("set_theme"), {"theme": "dark", "next": "/accounts/login/"})
        self.assertRedirects(r, "/accounts/login/")
        self.assertEqual(r.cookies["theme"].value, "dark")
        r = self.client.get(reverse("accounts:login"))
        self.assertContains(r, 'class="dark"')

    def test_theme_rejects_external_next_and_get(self):
        self.assertEqual(self.client.get(reverse("set_theme")).status_code, 405)
        r = self.client.post(reverse("set_theme"), {"theme": "light", "next": "https://evil.example/x"})
        self.assertEqual(r["Location"], "/")

    # ---- Template tags & filters ----
    def test_slot_when_12h_format(self):
        slot = TimeSlot(
            faculty=self.f,
            slot_date=datetime.date(2026, 11, 9),
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 30),
        )
        out = slot_when(slot)
        self.assertIn("9:00 AM", out)
        self.assertIn("10:30 AM", out)

    def test_friendly_day_labels(self):
        today = timezone.localdate()
        self.assertEqual(friendly_day(today), "Today")
        self.assertEqual(friendly_day(today + datetime.timedelta(days=1)), "Tomorrow")
        self.assertEqual(friendly_day(today - datetime.timedelta(days=1)), "Yesterday")

    def test_initials_and_status_badge(self):
        self.assertEqual(initials("Maria Clara"), "MC")
        self.assertEqual(initials(""), "?")
        self.assertIn("badge-pending", str(status_badge("PENDING")))
        self.assertIn("Pending", str(status_badge("PENDING")))

    # ---- Error pages ----
    def test_custom_403_for_wrong_role(self):
        self.client.force_login(self.s)
        r = self.client.get(reverse("scheduling:slot_list"))
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "Go to my dashboard", status_code=403)
        self.assertContains(r, "faculty accounts", status_code=403)

    @override_settings(DEBUG=False)
    def test_custom_404_and_500_templates(self):
        self.client.force_login(self.s)
        r = self.client.get("/nonexistent-path-xyz/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "404 · Not found", status_code=404)
        html_500 = render_to_string("500.html")
        self.assertIn("500 · Server error", html_500)

    # ---- History status filter & dashboard counts ----
    def test_history_status_tabs_and_filter(self):
        a1 = services.book_appointment(self.s, future_slot(self.f, hour=9), self.t, "First")
        a2 = services.book_appointment(self.s, future_slot(self.f, hour=10), self.t, "Second")
        services.change_status(a2, Status.APPROVED, self.f)
        self.client.force_login(self.s)
        r = self.client.get(reverse("scheduling:appointment_list") + "?status=APPROVED")
        self.assertContains(r, "Second")
        self.assertNotContains(r, "First")
        # Invalid status ignored -> shows all
        r_bad = self.client.get(reverse("scheduling:appointment_list") + "?status=BOGUS")
        self.assertContains(r_bad, "First")
        self.assertContains(r_bad, "Second")

    def test_dashboard_stat_counts(self):
        services.book_appointment(self.s, future_slot(self.f, hour=9), self.t, "One")
        self.client.force_login(self.f)
        r = self.client.get(reverse("scheduling:dashboard"))
        self.assertEqual(r.context["pending_count"], 1)
        self.assertEqual(r.context["slot_count"], 1)

    def test_new_figma_logo_and_static_assets_rendered(self):
        r_login = self.client.get(reverse("accounts:login"))
        self.assertContains(r_login, "logo-mark.svg")
        self.assertContains(r_login, "logo-mark-inverse.svg")
        self.assertContains(r_login, "appointed.css")
        self.assertContains(r_login, "code.jquery.com/jquery-3.7.1.min.js")
        self.assertNotContains(r_login, "appointed.js")

        self.client.force_login(self.f)
        r_dash = self.client.get(reverse("scheduling:dashboard"))
        self.assertContains(r_dash, "logo-mark-inverse.svg")
        self.assertContains(r_dash, f"Good morning, {self.f.full_name}.")
