from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from scheduling.models import Appointment, AppointmentLog, Status, TimeSlot


class SeedDemoTests(TestCase):
    def _run(self):
        call_command("seed_demo", stdout=StringIO())

    def test_idempotent_and_complete(self):
        self._run()
        counts = (User.objects.count(), TimeSlot.objects.count(),
                  Appointment.objects.count(), AppointmentLog.objects.count())
        self._run()
        self.assertEqual(counts, (User.objects.count(), TimeSlot.objects.count(),
                                  Appointment.objects.count(), AppointmentLog.objects.count()))
        self.assertEqual(User.objects.filter(role="ADMIN").count(), 1)
        self.assertEqual(User.objects.filter(role="FACULTY").count(), 3)
        self.assertEqual(User.objects.filter(role="STUDENT").count(), 3)
        for s in Status.values:
            self.assertTrue(Appointment.objects.filter(status=s).exists(), s)

    def test_demo_login_works(self):
        self._run()
        self.assertTrue(self.client.login(username="student1@demo.test", password="demo12345"))
        self.assertTrue(User.objects.get(email="admin@demo.test").is_staff)
