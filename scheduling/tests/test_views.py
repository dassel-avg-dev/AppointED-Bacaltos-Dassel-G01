from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, User
from scheduling import services
from scheduling.models import AppointmentType, Status

from .test_services import future_slot, make_users


class ViewTests(TestCase):
    def setUp(self):
        self.f, self.f2, self.s, self.s2 = make_users()
        self.t = AppointmentType.objects.first()

    def test_login_required(self):
        r = self.client.get(reverse("scheduling:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)

    def test_role_gating(self):
        self.client.force_login(self.s)
        self.assertEqual(self.client.get(reverse("scheduling:slot_list")).status_code, 403)
        self.client.force_login(self.f)
        self.assertEqual(self.client.get(reverse("scheduling:faculty_directory")).status_code, 403)

    def test_dashboards_render(self):
        for u in (self.s, self.f):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("scheduling:dashboard")).status_code, 200)

    def test_faculty_adds_and_deletes_slot(self):
        import datetime
        from django.utils import timezone
        self.client.force_login(self.f)
        d = (timezone.localtime() + datetime.timedelta(days=3)).date()
        r = self.client.post(reverse("scheduling:slot_create"),
                             {"slot_date": d, "start_time": "09:00", "end_time": "10:00"})
        self.assertRedirects(r, reverse("scheduling:slot_list"))
        slot = self.f.time_slots.get()
        self.client.post(reverse("scheduling:slot_delete", args=[slot.pk]))
        self.assertEqual(self.f.time_slots.count(), 0)

    def test_full_flow(self):
        slot = future_slot(self.f)
        self.client.force_login(self.s)
        self.assertEqual(self.client.get(reverse("scheduling:faculty_directory")).status_code, 200)
        self.assertContains(self.client.get(reverse("scheduling:faculty_slots", args=[self.f.pk])), "Book")
        r = self.client.post(reverse("scheduling:book", args=[slot.pk]),
                             {"type": self.t.pk, "purpose": "Thesis advice"})
        appt = slot.appointments.get()
        self.assertRedirects(r, reverse("scheduling:appointment_detail", args=[appt.pk]))
        # slot no longer open
        self.assertNotContains(self.client.get(reverse("scheduling:faculty_slots", args=[self.f.pk])),
                               "Thesis")
        self.client.force_login(self.f)
        self.client.post(reverse("scheduling:appointment_status", args=[appt.pk]), {"status": "APPROVED"})
        appt.refresh_from_db()
        self.assertEqual(appt.status, Status.APPROVED)
        self.assertContains(self.client.get(reverse("scheduling:appointment_detail", args=[appt.pk])), "Status history")

    def test_cross_user_access_404(self):
        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "x")
        for u in (self.s2, self.f2):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("scheduling:appointment_detail", args=[appt.pk])).status_code, 404)
            self.client.post(reverse("scheduling:appointment_status", args=[appt.pk]), {"status": "CANCELLED"})
        appt.refresh_from_db()
        self.assertEqual(appt.status, Status.PENDING)

    def test_status_requires_post(self):
        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "x")
        self.client.force_login(self.f)
        self.assertEqual(self.client.get(reverse("scheduling:appointment_status", args=[appt.pk])).status_code, 405)

    def test_admin_pages_and_actions(self):
        admin = User.objects.create_superuser("root@x.com", "pw", full_name="Root")
        appt = services.book_appointment(self.s, future_slot(self.f), self.t, "x")
        self.client.force_login(admin)
        for name in ("user", "department"):
            self.assertEqual(self.client.get(f"/admin/accounts/{name}/").status_code, 200)
        for name in ("timeslot", "appointment", "appointmenttype", "appointmentlog"):
            self.assertEqual(self.client.get(f"/admin/scheduling/{name}/").status_code, 200)
        self.client.post("/admin/scheduling/appointment/",
                         {"action": "approve", "_selected_action": [appt.pk]})
        appt.refresh_from_db()
        self.assertEqual(appt.status, Status.APPROVED)
        self.assertEqual(appt.logs.count(), 2)

    def test_faculty_edits_unbooked_slot(self):
        import datetime
        from django.utils import timezone
        slot = future_slot(self.f, days=3, hour=9, length=1)
        self.client.force_login(self.f)
        url = reverse("scheduling:slot_edit", args=[slot.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        new_date = (timezone.localtime() + datetime.timedelta(days=4)).date()
        r = self.client.post(url, {"slot_date": new_date, "start_time": "10:00", "end_time": "11:30"})
        self.assertRedirects(r, reverse("scheduling:slot_list"))
        slot.refresh_from_db()
        self.assertEqual(slot.slot_date, new_date)
        self.assertEqual(slot.start_time, datetime.time(10, 0))
        self.assertEqual(slot.end_time, datetime.time(11, 30))

    def test_slot_edit_gating_and_booked_rejection(self):
        slot = future_slot(self.f)
        url = reverse("scheduling:slot_edit", args=[slot.pk])
        self.client.force_login(self.s)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.f2)
        self.assertEqual(self.client.get(url).status_code, 404)
        services.book_appointment(self.s, slot, self.t, "Advising")
        self.client.force_login(self.f)
        r = self.client.get(url)
        self.assertRedirects(r, reverse("scheduling:slot_list"))

    def test_faculty_directory_filters(self):
        ccs = Department.objects.create(name="CCS")
        eng = Department.objects.create(name="Engineering")
        self.f.department = ccs
        self.f.save(update_fields=["department"])
        self.f2.department = eng
        self.f2.save(update_fields=["department"])
        self.client.force_login(self.s)
        r = self.client.get(reverse("scheduling:faculty_directory"), {"department": ccs.pk})
        self.assertContains(r, self.f.full_name)
        self.assertNotContains(r, self.f2.full_name)
        r2 = self.client.get(reverse("scheduling:faculty_directory"), {"q": "Fac2"})
        self.assertContains(r2, self.f2.full_name)
        self.assertNotContains(r2, "Fac\n")

    def test_appointment_list_search_and_type_filter(self):
        t2 = AppointmentType.objects.exclude(pk=self.t.pk).first()
        services.book_appointment(self.s, future_slot(self.f, days=2, hour=9), self.t, "Thesis outline")
        services.book_appointment(self.s, future_slot(self.f, days=2, hour=11), t2, "Clearance form")
        self.client.force_login(self.s)
        r = self.client.get(reverse("scheduling:appointment_list"), {"q": "Thesis"})
        self.assertContains(r, "Thesis outline")
        self.assertNotContains(r, "Clearance form")
        r2 = self.client.get(reverse("scheduling:appointment_list"), {"type": t2.pk})
        self.assertContains(r2, "Clearance form")
        self.assertNotContains(r2, "Thesis outline")
