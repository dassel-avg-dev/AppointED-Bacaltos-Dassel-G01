"""Business-rule enforcement. All slot/appointment mutations go through here."""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from .models import Appointment, AppointmentLog, Status, TimeSlot


class BusinessRuleError(Exception):
    pass


def _validate_slot_window(faculty, slot_date, start_time, end_time, exclude_pk=None):
    if not faculty.is_faculty:  # BR-05
        raise BusinessRuleError("Only faculty can manage time slots.")
    if end_time <= start_time:  # BR-03
        raise BusinessRuleError("End time must be later than start time.")
    slot = TimeSlot(faculty=faculty, slot_date=slot_date, start_time=start_time, end_time=end_time)
    if slot.start_datetime <= timezone.now():  # X1
        raise BusinessRuleError("Time slots cannot be scheduled in the past.")
    dup_qs = TimeSlot.objects.filter(faculty=faculty, slot_date=slot_date, start_time=start_time)
    if exclude_pk is not None:
        dup_qs = dup_qs.exclude(pk=exclude_pk)
    if dup_qs.exists():
        raise BusinessRuleError("You already have a slot starting at that date and time.")  # BR-04
    overlap_qs = TimeSlot.objects.filter(  # X2
        faculty=faculty, slot_date=slot_date, start_time__lt=end_time, end_time__gt=start_time
    )
    if exclude_pk is not None:
        overlap_qs = overlap_qs.exclude(pk=exclude_pk)
    if overlap_qs.exists():
        raise BusinessRuleError("This slot overlaps one of your existing slots.")
    return slot


@transaction.atomic
def create_slot(faculty, slot_date, start_time, end_time):
    slot = _validate_slot_window(faculty, slot_date, start_time, end_time)
    try:
        with transaction.atomic():
            slot.save()
    except IntegrityError:
        raise BusinessRuleError("You already have a slot starting at that date and time.")
    return slot


@transaction.atomic
def update_slot(faculty, slot, slot_date, start_time, end_time):
    slot = TimeSlot.objects.select_for_update().get(pk=slot.pk)
    if slot.faculty_id != faculty.pk:
        raise BusinessRuleError("You can only edit your own slots.")
    if slot.appointments.exists():  # BR-13
        raise BusinessRuleError("A slot that has appointments cannot be edited.")
    _validate_slot_window(faculty, slot_date, start_time, end_time, exclude_pk=slot.pk)
    slot.slot_date = slot_date
    slot.start_time = start_time
    slot.end_time = end_time
    try:
        with transaction.atomic():
            slot.save(update_fields=["slot_date", "start_time", "end_time"])
    except IntegrityError:
        raise BusinessRuleError("You already have a slot starting at that date and time.")
    return slot


@transaction.atomic
def delete_slot(faculty, slot):
    slot = TimeSlot.objects.select_for_update().get(pk=slot.pk)
    if slot.faculty_id != faculty.pk:
        raise BusinessRuleError("You can only delete your own slots.")
    if slot.appointments.exists():  # BR-13
        raise BusinessRuleError("A slot that has appointments cannot be deleted.")
    try:
        with transaction.atomic():
            slot.delete()
    except ProtectedError:
        raise BusinessRuleError("A slot that has appointments cannot be deleted.")


def _log(appointment, old, new, actor):
    AppointmentLog.objects.create(
        appointment=appointment, changed_by=actor, old_status=old, new_status=new
    )


@transaction.atomic
def book_appointment(student, slot, appt_type, purpose):
    if not student.is_student:  # BR-06
        raise BusinessRuleError("Only students can book appointments.")
    purpose = (purpose or "").strip()
    if not purpose:  # BR-14
        raise BusinessRuleError("A purpose is required.")
    slot = TimeSlot.objects.select_for_update().get(pk=slot.pk)
    if slot.has_started:  # X3
        raise BusinessRuleError("This slot has already started or passed.")
    if slot.appointments.exclude(status=Status.CANCELLED).exists():  # BR-07
        raise BusinessRuleError("This slot has just been taken.")
    try:
        with transaction.atomic():
            appt = Appointment.objects.create(
                student=student, slot=slot, type=appt_type, purpose=purpose
            )
    except IntegrityError:
        raise BusinessRuleError("This slot has just been taken.")
    _log(appt, None, Status.PENDING, student)
    return appt


# (old_status, new_status) -> who may do it: "owner_faculty" and/or "owner_student"
TRANSITIONS = {
    (Status.PENDING, Status.APPROVED): {"faculty"},
    (Status.PENDING, Status.CANCELLED): {"faculty", "student"},  # BR-12
    (Status.APPROVED, Status.CANCELLED): {"faculty"},  # X4
    (Status.APPROVED, Status.COMPLETED): {"faculty"},  # BR-11
}


def allowed_actions(appointment, actor):
    """Target statuses `actor` may currently set (ignoring timing rules except X5)."""
    result = []
    for (old, new), roles in TRANSITIONS.items():
        if old != appointment.status:
            continue
        if "faculty" in roles and appointment.slot.faculty_id == actor.pk and actor.is_faculty:
            ok = True
        elif "student" in roles and appointment.student_id == actor.pk and actor.is_student:
            ok = True
        elif actor.is_admin_role:
            ok = True
        else:
            ok = False
        if ok and new == Status.COMPLETED and not appointment.slot.has_ended:  # X5
            ok = False
        if ok:
            result.append(new)
    return result


@transaction.atomic
def change_status(appointment, new_status, actor):
    appointment = Appointment.objects.select_for_update().select_related("slot").get(
        pk=appointment.pk
    )
    old = appointment.status
    roles = TRANSITIONS.get((old, new_status))
    if roles is None:
        raise BusinessRuleError(f"An appointment cannot go from {old} to {new_status}.")
    is_owner_faculty = actor.is_faculty and appointment.slot.faculty_id == actor.pk
    is_owner_student = actor.is_student and appointment.student_id == actor.pk
    if not (
        actor.is_admin_role
        or ("faculty" in roles and is_owner_faculty)
        or ("student" in roles and is_owner_student)
    ):
        raise BusinessRuleError("You are not allowed to make this change.")  # BR-10 / BR-12
    if new_status == Status.COMPLETED and not appointment.slot.has_ended:  # X5
        raise BusinessRuleError("An appointment can be completed only after the slot has ended.")
    appointment.status = new_status
    appointment.save(update_fields=["status", "updated_at"])
    _log(appointment, old, new_status, actor)
    return appointment
