import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department, User
from scheduling import services
from scheduling.models import AppointmentLog, AppointmentType, Status, TimeSlot
from scheduling.tests.test_services import future_slot, make_users


class AdminPanelTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.admin = User.objects.create_superuser(
            "paneladmin@x.com", "pw123456", full_name="Panel Admin"
        )
        self.t = AppointmentType.objects.first()

    # ---- Access Control & Routing ----
    def test_admin_panel_requires_admin_role(self):
        urls = [
            reverse("admin_panel:overview"),
            reverse("admin_panel:user_list"),
            reverse("admin_panel:user_create"),
            reverse("admin_panel:appointment_list"),
            reverse("admin_panel:slot_list"),
            reverse("admin_panel:slot_create"),
            reverse("admin_panel:department_list"),
            reverse("admin_panel:type_list"),
            reverse("admin_panel:audit_logs"),
        ]
        # Anonymous -> login redirect
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("accounts:login"), r.url)

        # Student & Faculty -> 403
        for user in (self.s, self.f):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, f"{user.role} {url}")

        # Admin -> 200
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_dashboard_redirects_to_custom_panel_and_default_admin_still_works(self):
        self.client.force_login(self.admin)
        self.assertRedirects(
            self.client.get(reverse("scheduling:dashboard")),
            reverse("admin_panel:overview"),
        )
        # Option A: classic Django admin remains accessible at /admin/
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    # ---- User Management ----
    def test_admin_creates_edits_and_toggles_user_and_blocks_self_deactivate(self):
        dept = Department.objects.first()
        self.client.force_login(self.admin)

        # Create user
        r = self.client.post(
            reverse("admin_panel:user_create"),
            {
                "email": "NewFac@University.Edu",
                "full_name": "Dr. New Faculty",
                "role": User.Role.FACULTY,
                "department": dept.pk,
                "is_active": "on",
                "new_password": "StrongPassword99!",
            },
        )
        self.assertRedirects(r, reverse("admin_panel:user_list"))
        created = User.objects.get(email="newfac@university.edu")
        self.assertTrue(created.check_password("StrongPassword99!"))

        # Edit without changing password
        r_edit = self.client.post(
            reverse("admin_panel:user_edit", args=[created.pk]),
            {
                "email": "newfac@university.edu",
                "full_name": "Dr. Renamed Faculty",
                "role": User.Role.FACULTY,
                "department": dept.pk,
                "is_active": "on",
                "new_password": "",
            },
        )
        self.assertRedirects(r_edit, reverse("admin_panel:user_list"))
        created.refresh_from_db()
        self.assertEqual(created.full_name, "Dr. Renamed Faculty")
        self.assertTrue(created.check_password("StrongPassword99!"))

        # Toggle active off
        self.client.post(reverse("admin_panel:user_toggle_active", args=[created.pk]))
        created.refresh_from_db()
        self.assertFalse(created.is_active)

        # Cannot deactivate self
        r_self = self.client.post(
            reverse("admin_panel:user_toggle_active", args=[self.admin.pk]), follow=True
        )
        self.assertContains(r_self, "You cannot deactivate your own account.")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # ---- Appointments & Audit Trail ----
    def test_admin_approves_and_cancels_appointment_with_audit_log(self):
        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "Capstone check")
        self.client.force_login(self.admin)

        r = self.client.post(
            reverse("admin_panel:appointment_status", args=[appt.pk]),
            {"status": Status.APPROVED},
        )
        self.assertRedirects(r, reverse("admin_panel:appointment_detail", args=[appt.pk]))
        appt.refresh_from_db()
        self.assertEqual(appt.status, Status.APPROVED)
        self.assertEqual(AppointmentLog.objects.filter(appointment=appt).count(), 2)

        r_logs = self.client.get(reverse("admin_panel:audit_logs"))
        self.assertContains(r_logs, "Panel Admin")

    # ---- Slots ----
    def test_admin_manages_faculty_slots_and_protects_booked_slot(self):
        self.client.force_login(self.admin)
        d = (timezone.localtime() + datetime.timedelta(days=4)).date()
        r = self.client.post(
            reverse("admin_panel:slot_create"),
            {"faculty": self.f.pk, "slot_date": d, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertRedirects(r, reverse("admin_panel:slot_list"))
        slot = TimeSlot.objects.get(faculty=self.f, slot_date=d)

        # Edit open slot
        r_edit = self.client.post(
            reverse("admin_panel:slot_edit", args=[slot.pk]),
            {"faculty": self.f.pk, "slot_date": d, "start_time": "10:00", "end_time": "11:00"},
        )
        self.assertRedirects(r_edit, reverse("admin_panel:slot_list"))
        slot.refresh_from_db()
        self.assertEqual(slot.start_time, datetime.time(10, 0))

        # Booked slot cannot be deleted
        services.book_appointment(self.s, slot, self.t, "Advising")
        r_del = self.client.post(reverse("admin_panel:slot_delete", args=[slot.pk]), follow=True)
        self.assertContains(r_del, "cannot be deleted")
        self.assertTrue(TimeSlot.objects.filter(pk=slot.pk).exists())

    # ---- Catalog: Departments & Appointment Types ----
    def test_admin_catalog_crud_and_protected_type_guard(self):
        self.client.force_login(self.admin)

        r_dept = self.client.post(reverse("admin_panel:department_list"), {"name": "School of Law"})
        self.assertRedirects(r_dept, reverse("admin_panel:department_list"))
        dept = Department.objects.get(name="School of Law")
        self.client.post(reverse("admin_panel:department_delete", args=[dept.pk]))
        self.assertFalse(Department.objects.filter(pk=dept.pk).exists())

        # Referenced appointment type cannot be deleted
        services.book_appointment(self.s, future_slot(self.f), self.t, "Check")
        r_del_type = self.client.post(
            reverse("admin_panel:type_delete", args=[self.t.pk]), follow=True
        )
        self.assertContains(r_del_type, "Cannot delete")
        self.assertTrue(AppointmentType.objects.filter(pk=self.t.pk).exists())
