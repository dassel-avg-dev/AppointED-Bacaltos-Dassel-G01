import datetime

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone


class Status(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class TimeSlot(models.Model):
    slot_id = models.AutoField(primary_key=True)
    faculty = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="faculty_id",
        related_name="time_slots",
    )
    slot_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())

    class Meta:
        db_table = "time_slots"
        ordering = ["slot_date", "start_time"]
        constraints = [
            models.CheckConstraint(  # BR-03
                condition=Q(end_time__gt=F("start_time")), name="time_slots_end_after_start"
            ),
            models.UniqueConstraint(  # BR-04
                fields=["faculty", "slot_date", "start_time"],
                name="time_slots_faculty_date_start_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.faculty.full_name} {self.slot_date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def _aware(self, t):
        return timezone.make_aware(datetime.datetime.combine(self.slot_date, t))

    @property
    def start_datetime(self):
        return self._aware(self.start_time)

    @property
    def end_datetime(self):
        return self._aware(self.end_time)

    @property
    def has_started(self):
        return self.start_datetime <= timezone.now()

    @property
    def has_ended(self):
        return self.end_datetime <= timezone.now()

    @property
    def active_appointment(self):
        if hasattr(self, "_prefetched_objects_cache") and "appointments" in self._prefetched_objects_cache:
            return next((a for a in self.appointments.all() if a.status != Status.CANCELLED), None)
        return self.appointments.exclude(status=Status.CANCELLED).first()

    @property
    def is_open(self):
        return not self.has_started and self.active_appointment is None


class AppointmentType(models.Model):
    type_id = models.AutoField(primary_key=True)
    type_name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "appointment_types"
        ordering = ["type_name"]

    def __str__(self):
        return self.type_name


class Appointment(models.Model):
    appointment_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="student_id",
        related_name="appointments",
    )
    slot = models.ForeignKey(  # BR-13
        TimeSlot, on_delete=models.PROTECT, db_column="slot_id", related_name="appointments"
    )
    type = models.ForeignKey(AppointmentType, on_delete=models.PROTECT, db_column="type_id")
    purpose = models.CharField(max_length=255)  # BR-14
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_default=Status.PENDING
    )  # BR-09
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "appointments"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(  # BR-08
                condition=Q(status__in=Status.values), name="appointments_status_check"
            ),
            models.UniqueConstraint(  # BR-07
                fields=["slot"],
                condition=~Q(status="CANCELLED"),
                name="appointments_one_active_per_slot",
            ),
            models.CheckConstraint(
                condition=~Q(purpose=""), name="appointments_purpose_not_blank"
            ),
        ]

    def __str__(self):
        return f"Appointment #{self.appointment_id} ({self.status})"


class AppointmentLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.CASCADE, db_column="appointment_id", related_name="logs"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="changed_by",
        related_name="+",
    )
    old_status = models.CharField(max_length=10, null=True, blank=True)
    new_status = models.CharField(max_length=10, choices=Status.choices)
    changed_at = models.DateTimeField(auto_now_add=True, db_default=Now())

    class Meta:
        db_table = "appointment_logs"
        ordering = ["changed_at", "log_id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(new_status__in=Status.values),
                name="appointment_logs_new_status_check",
            )
        ]

    def __str__(self):
        return f"{self.old_status} -> {self.new_status}"
