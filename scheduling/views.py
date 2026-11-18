from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import faculty_required, student_required
from accounts.models import Department, User

from . import services
from .forms import BookingForm, TimeSlotForm
from .models import Appointment, AppointmentType, Status, TimeSlot
from .services import BusinessRuleError


def _appointments_for(user):
    qs = Appointment.objects.select_related("slot", "slot__faculty", "student", "type")
    if user.is_faculty:
        return qs.filter(slot__faculty=user)
    if user.is_student:
        return qs.filter(student=user)
    return qs.none()


@login_required
def dashboard(request):
    user = request.user
    if user.is_admin_role:
        return redirect("admin:index")
    appts = list(_appointments_for(user))
    if user.is_faculty:
        for a in appts:
            a.actions = services.allowed_actions(a, user)
        pending = [a for a in appts if a.status == Status.PENDING]
        approved = [a for a in appts if a.status == Status.APPROVED]
        slots = list(user.time_slots.prefetch_related("appointments"))
        return render(
            request,
            "scheduling/faculty_dashboard.html",
            {
                "pending": pending,
                "approved": approved,
                "pending_count": len(pending),
                "approved_count": len(approved),
                "completed_count": sum(1 for a in appts if a.status == Status.COMPLETED),
                "open_slots": sum(1 for s in slots if s.is_open),
                "slot_count": len(slots),
            },
        )
    for a in appts:
        a.actions = services.allowed_actions(a, user)
    active = [a for a in appts if a.status in (Status.PENDING, Status.APPROVED)]
    return render(
        request,
        "scheduling/student_dashboard.html",
        {
            "appointments": active,
            "pending_count": sum(1 for a in appts if a.status == Status.PENDING),
            "approved_count": sum(1 for a in appts if a.status == Status.APPROVED),
            "completed_count": sum(1 for a in appts if a.status == Status.COMPLETED),
            "total_count": len(appts),
        },
    )


# ---- Faculty: slots ----
@faculty_required
def slot_list(request):
    rows = []
    for s in request.user.time_slots.prefetch_related("appointments", "appointments__student"):
        all_appts = list(s.appointments.all())
        active = [a for a in all_appts if a.status != Status.CANCELLED]
        rows.append(
            {
                "slot": s,
                "slot_date": s.slot_date,
                "active": active[0] if active else None,
                "deletable": not all_appts,
            }
        )
    return render(request, "scheduling/slot_list.html", {"rows": rows})


@faculty_required
def slot_create(request):
    form = TimeSlotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.create_slot(request.user, **form.cleaned_data)
        except BusinessRuleError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Time slot added.")
            return redirect("scheduling:slot_list")
    return render(request, "scheduling/slot_form.html", {"form": form})


@faculty_required
def slot_edit(request, slot_id):
    slot = get_object_or_404(TimeSlot, pk=slot_id, faculty=request.user)
    if slot.appointments.exists():
        messages.error(request, "A slot that has appointments cannot be edited.")
        return redirect("scheduling:slot_list")
    form = TimeSlotForm(
        request.POST or None,
        initial={"slot_date": slot.slot_date, "start_time": slot.start_time, "end_time": slot.end_time},
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.update_slot(request.user, slot, **form.cleaned_data)
        except BusinessRuleError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Time slot updated.")
            return redirect("scheduling:slot_list")
    return render(request, "scheduling/slot_form.html", {"form": form, "slot": slot, "is_edit": True})


@faculty_required
@require_POST
def slot_delete(request, slot_id):
    slot = get_object_or_404(TimeSlot, pk=slot_id, faculty=request.user)
    try:
        services.delete_slot(request.user, slot)
        messages.success(request, "Time slot deleted.")
    except BusinessRuleError as e:
        messages.error(request, str(e))
    return redirect("scheduling:slot_list")


# ---- Student: browse and book ----
@student_required
def faculty_directory(request):
    query = request.GET.get("q", "").strip()
    selected_department = request.GET.get("department", "").strip()
    faculty = (
        User.objects.filter(role=User.Role.FACULTY, is_active=True)
        .select_related("department")
        .prefetch_related("time_slots__appointments")
    )
    if query:
        faculty = faculty.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
    if selected_department.isdigit():
        faculty = faculty.filter(department_id=int(selected_department))
    else:
        selected_department = ""
    rows = [
        {"faculty": f, "open_count": sum(1 for s in f.time_slots.all() if s.is_open)}
        for f in faculty
    ]
    return render(
        request,
        "scheduling/faculty_directory.html",
        {
            "rows": rows,
            "departments": Department.objects.all(),
            "query": query,
            "selected_department": selected_department,
        },
    )


@student_required
def faculty_slots(request, user_id):
    faculty = get_object_or_404(
        User.objects.select_related("department"), pk=user_id, role=User.Role.FACULTY, is_active=True
    )
    slots = [s for s in faculty.time_slots.all() if s.is_open]
    return render(request, "scheduling/faculty_slots.html", {"faculty": faculty, "slots": slots})


@student_required
def book(request, slot_id):
    slot = get_object_or_404(
        TimeSlot.objects.select_related("faculty", "faculty__department"), pk=slot_id
    )
    form = BookingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            appt = services.book_appointment(
                request.user, slot, form.cleaned_data["type"], form.cleaned_data["purpose"]
            )
        except BusinessRuleError as e:
            messages.error(request, str(e))
            return redirect("scheduling:faculty_slots", user_id=slot.faculty_id)
        messages.success(request, "Appointment requested. Waiting for faculty approval.")
        return redirect("scheduling:appointment_detail", appointment_id=appt.pk)
    return render(request, "scheduling/book.html", {"slot": slot, "form": form})


# ---- History / detail / status ----
@login_required
def appointment_list(request):
    if request.user.is_admin_role:
        return redirect("admin:index")
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("type", "").strip()
    qs = _appointments_for(request.user)
    if query:
        qs = qs.filter(
            Q(purpose__icontains=query)
            | Q(student__full_name__icontains=query)
            | Q(slot__faculty__full_name__icontains=query)
        )
    if selected_type.isdigit():
        qs = qs.filter(type_id=int(selected_type))
    else:
        selected_type = ""
    all_appts = list(qs)
    active_status = request.GET.get("status", "")
    if active_status not in Status.values:
        active_status = ""
    filtered = [a for a in all_appts if not active_status or a.status == active_status]
    tabs = [("", "All", len(all_appts))] + [
        (s.value, s.label, sum(1 for a in all_appts if a.status == s.value)) for s in Status
    ]
    filter_params = {}
    if query:
        filter_params["q"] = query
    if selected_type:
        filter_params["type"] = selected_type
    base_query = urlencode(filter_params)
    return render(
        request,
        "scheduling/appointment_list.html",
        {
            "appointments": filtered,
            "tabs": tabs,
            "active_status": active_status,
            "appointment_types": AppointmentType.objects.all(),
            "query": query,
            "selected_type": selected_type,
            "base_query": base_query,
        },
    )


@login_required
def appointment_detail(request, appointment_id):
    appt = get_object_or_404(_appointments_for(request.user), pk=appointment_id)
    return render(
        request,
        "scheduling/appointment_detail.html",
        {
            "appt": appt,
            "logs": appt.logs.select_related("changed_by"),
            "actions": services.allowed_actions(appt, request.user),
        },
    )


@login_required
@require_POST
def appointment_status(request, appointment_id):
    appt = get_object_or_404(_appointments_for(request.user), pk=appointment_id)
    new_status = request.POST.get("status")
    if new_status not in Status.values:
        raise Http404
    try:
        services.change_status(appt, new_status, request.user)
        messages.success(request, f"Appointment marked {new_status.title()}.")
    except BusinessRuleError as e:
        messages.error(request, str(e))
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("scheduling:appointment_detail", appointment_id=appt.pk)
