from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, User


class AccountTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.first()

    def _reg(self, **over):
        data = {
            "email": "a@x.com", "full_name": "A", "role": "STUDENT", "department": self.dept.pk,
            "password1": "S3cure-pass-99", "password2": "S3cure-pass-99",
        }
        data.update(over)
        return self.client.post(reverse("accounts:register"), data)

    def test_register_student_and_faculty(self):
        self._reg()
        self.client.logout()
        self._reg(email="f@x.com", role="FACULTY")
        self.assertEqual(User.objects.get(email="a@x.com").role, "STUDENT")
        self.assertEqual(User.objects.get(email="f@x.com").role, "FACULTY")

    def test_cannot_register_admin(self):
        r = self._reg(role="ADMIN")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="a@x.com").exists())

    def test_duplicate_email_rejected(self):  # BR-01
        User.objects.create_user("a@x.com", "pw", full_name="A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("a@x.com", "pw", full_name="B")

    def test_role_check_constraint(self):  # BR-02
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("b@x.com", "pw", full_name="B", role="HACKER")

    def test_registration_shows_success_message(self):
        r = self.client.post(
            reverse("accounts:register"),
            {
                "email": "a@x.com", "full_name": "A", "role": "STUDENT",
                "department": self.dept.pk,
                "password1": "S3cure-pass-99", "password2": "S3cure-pass-99",
            },
            follow=True,
        )
        self.assertContains(r, "Your account was created successfully.")

    def test_login_with_email(self):
        User.objects.create_user("a@x.com", "S3cure-pass-99", full_name="A")
        r = self.client.post(
            reverse("accounts:login"),
            {"username": "a@x.com", "password": "S3cure-pass-99"},
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], 302)
        self.assertContains(r, "You are now logged in.")

    def test_invalid_login_shows_error(self):
        r = self.client.post(
            reverse("accounts:login"),
            {"username": "missing@x.com", "password": "wrong"},
        )
        self.assertContains(r, "Please enter a correct email and password.")

    def test_logout_shows_success_message(self):
        user = User.objects.create_user("a@x.com", "pw", full_name="A")
        self.client.force_login(user)
        r = self.client.post(reverse("accounts:logout"), follow=True)
        self.assertContains(r, "You have been logged out.")

    def test_superuser_is_admin_with_admin_access(self):
        u = User.objects.create_superuser("root@x.com", "pw", full_name="Root")
        self.assertEqual(u.role, "ADMIN")
        self.assertTrue(u.is_staff)
        self.client.force_login(u)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
