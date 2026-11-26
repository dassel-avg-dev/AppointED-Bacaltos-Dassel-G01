from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import Department, User
from scheduling import services
from scheduling.models import Appointment, AppointmentLog, AppointmentType, Status, TimeSlot
from scheduling.services import BusinessRuleError

from .forms import AdminTimeSlotForm, AdminUserForm, AppointmentTypeForm, DepartmentForm


@admin_required
def overview(request):
    users = list(User.objects.only("user_id", "role", "is_active"))
    appts = list(
        Appointment.objects.select_related("slot", "slot__faculty", "student", "type")
    )
    slots = list(TimeSlot.objects.prefetch_related("appointments"))

    pending = [a for a in appts if a.status == Status.PENDING]
    for a in pending[:6]:
        a.actions = services.allowed_actions(a, request.user)

    recent_logs = list(
        AppointmentLog.objects.select_related(
            "appointment", "appointment__student", "appointment__slot__faculty", "changed_by"
        ).order_by("-changed_at", "-log_id")[:8]
    )

    return render(
        request,
        "admin_panel/overview.html",
        {
            "total_users": len(users),
            "active_users": sum(1 for u in users if u.is_active),
            "faculty_count": sum(1 for u in users if u.role == User.Role.FACULTY),
            "student_count": sum(1 for u in users if u.role == User.Role.STUDENT),
            "pending_count": len(pending),
            "approved_count": sum(1 for a in appts if a.status == Status.APPROVED),
            "completed_count": sum(1 for a in appts if a.status == Status.COMPLETED),
            "open_slots": sum(1 for s in slots if s.is_open),
            "total_slots": len(slots),
            "pending_queue": pending[:6],
            "recent_logs": recent_logs,
        },
    )


# ---- Users ----
@admin_required
def user_list(request):
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    department = request.GET.get("department", "").strip()
    active = request.GET.get("active", "").strip()

    qs = User.objects.select_related("department").order_by("-created_at")
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
    if role in User.Role.values:
        qs = qs.filter(role=role)
    else:
        role = ""
    if department.isdigit():
        qs = qs.filter(department_id=int(department))
    else:
        department = ""
    if active == "1":
        qs = qs.filter(is_active=True)
    elif active == "0":
        qs = qs.filter(is_active=False)
    else:
        active = ""

    return render(
        request,
        "admin_panel/user_list.html",
        {
            "users": qs,
            "roles": User.Role.choices,
            "departments": Department.objects.all(),
            "query": query,
            "selected_role": role,
            "selected_department": department,
            "selected_active": active,
        },
    )


@admin_required
def user_create(request):
    form = AdminUserForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Created account for {user.full_name}.")
            return redirect("admin_panel:user_list")
        messages.error(request, "Please correct the errors below.")
    return render(request, "admin_panel/user_form.html", {"form": form, "is_edit": False})


@admin_required
def user_edit(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    form = AdminUserForm(request.POST or None, instance=target)
    if request.method == "POST":
        if form.is_valid():
            if target.pk == request.user.pk and not form.cleaned_data.get("is_active", True):
                form.add_error("is_active", "You cannot deactivate your own account.")
                messages.error(request, "You cannot deactivate your own account.")
            else:
                form.save()
                messages.success(request, f"Updated {target.full_name}.")
                return redirect("admin_panel:user_list")
        else:
            messages.error(request, "Please correct the errors below.")
    return render(
        request,
        "admin_panel/user_form.html",
        {"form": form, "target_user": target, "is_edit": True},
    )


@admin_required
@require_POST
def user_toggle_active(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("admin_panel:user_list")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    state_label = "activated" if target.is_active else "deactivated"
    messages.success(request, f"{target.full_name} has been {state_label}.")
    return redirect("admin_panel:user_list")


# ---- Appointments ----
@admin_required
def appointment_list(request):
    query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("type", "").strip()

    qs = Appointment.objects.select_related("slot", "slot__faculty", "student", "type")
    if query:
        qs = qs.filter(
            Q(purpose__icontains=query)
            | Q(student__full_name__icontains=query)
            | Q(student__email__icontains=query)
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
    for a in filtered:
        a.actions = services.allowed_actions(a, request.user)

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
        "admin_panel/appointment_list.html",
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


@admin_required
def appointment_detail(request, appointment_id):
    appt = get_object_or_404(
        Appointment.objects.select_related("slot", "slot__faculty", "student", "type"),
        pk=appointment_id,
    )
    return render(
        request,
        "admin_panel/appointment_detail.html",
        {
            "appt": appt,
            "logs": appt.logs.select_related("changed_by"),
            "actions": services.allowed_actions(appt, request.user),
        },
    )


@admin_required
@require_POST
def appointment_status(request, appointment_id):
    appt = get_object_or_404(Appointment.objects.select_related("slot"), pk=appointment_id)
    new_status = request.POST.get("status")
    if new_status not in Status.values:
        raise Http404
    try:
        services.change_status(appt, new_status, request.user)
        messages.success(request, f"Appointment #{appt.pk} marked {new_status.title()}.")
    except BusinessRuleError as e:
        messages.error(request, str(e))
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("admin_panel:appointment_detail", appointment_id=appt.pk)


# ---- Time Slots ----
@admin_required
def slot_list(request):
    selected_faculty = request.GET.get("faculty", "").strip()
    selected_department = request.GET.get("department", "").strip()
    state_filter = request.GET.get("state", "").strip()

    qs = TimeSlot.objects.select_related("faculty", "faculty__department").prefetch_related(
        "appointments", "appointments__student"
    )
    if selected_faculty.isdigit():
        qs = qs.filter(faculty_id=int(selected_faculty))
    else:
        selected_faculty = ""
    if selected_department.isdigit():
        qs = qs.filter(faculty__department_id=int(selected_department))
    else:
        selected_department = ""

    rows = []
    for s in qs:
        all_appts = list(s.appointments.all())
        active = [a for a in all_appts if a.status != Status.CANCELLED]
        slot_state = "booked" if active else ("past" if s.has_started else "open")
        if state_filter in ("open", "booked", "past") and slot_state != state_filter:
            continue
        rows.append(
            {
                "slot": s,
                "slot_date": s.slot_date,
                "active": active[0] if active else None,
                "deletable": not all_appts,
                "state": slot_state,
            }
        )

    return render(
        request,
        "admin_panel/slot_list.html",
        {
            "rows": rows,
            "faculty_members": User.objects.filter(role=User.Role.FACULTY).order_by("full_name"),
            "departments": Department.objects.all(),
            "selected_faculty": selected_faculty,
            "selected_department": selected_department,
            "state_filter": state_filter,
        },
    )


@admin_required
def slot_create(request):
    form = AdminTimeSlotForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data
            try:
                services.create_slot(cd["faculty"], cd["slot_date"], cd["start_time"], cd["end_time"])
            except BusinessRuleError as e:
                form.add_error(None, str(e))
                messages.error(request, str(e))
            else:
                messages.success(request, f"Time slot added for {cd['faculty'].full_name}.")
                return redirect("admin_panel:slot_list")
        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, "admin_panel/slot_form.html", {"form": form, "is_edit": False})


@admin_required
def slot_edit(request, slot_id):
    slot = get_object_or_404(TimeSlot.objects.select_related("faculty"), pk=slot_id)
    if slot.appointments.exists():
        messages.error(request, "A slot that has appointments cannot be edited.")
        return redirect("admin_panel:slot_list")
    if slot.has_started:
        messages.error(request, "Past time slots cannot be edited.")
        return redirect("admin_panel:slot_list")

    form = AdminTimeSlotForm(
        request.POST or None,
        is_edit=True,
        initial={
            "faculty": slot.faculty,
            "slot_date": slot.slot_date,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
        },
    )
    if request.method == "POST":
        if form.is_valid():
            cd = form.cleaned_data
            try:
                services.update_slot(slot.faculty, slot, cd["slot_date"], cd["start_time"], cd["end_time"])
            except BusinessRuleError as e:
                form.add_error(None, str(e))
                messages.error(request, str(e))
            else:
                messages.success(request, "Time slot updated.")
                return redirect("admin_panel:slot_list")
        else:
            messages.error(request, "Please correct the errors below.")
    return render(
        request,
        "admin_panel/slot_form.html",
        {"form": form, "slot": slot, "is_edit": True},
    )


@admin_required
@require_POST
def slot_delete(request, slot_id):
    slot = get_object_or_404(TimeSlot.objects.select_related("faculty"), pk=slot_id)
    try:
        services.delete_slot(slot.faculty, slot)
        messages.success(request, "Time slot deleted.")
    except BusinessRuleError as e:
        messages.error(request, str(e))
    return redirect("admin_panel:slot_list")


# ---- Catalog: Departments & Appointment Types ----
@admin_required
def department_list(request):
    edit_id = request.GET.get("edit", "").strip()
    edit_obj = get_object_or_404(Department, pk=int(edit_id)) if edit_id.isdigit() else None

    if request.method == "POST":
        post_edit_id = request.POST.get("edit_id", "").strip()
        instance = get_object_or_404(Department, pk=int(post_edit_id)) if post_edit_id.isdigit() else None
        form = DepartmentForm(request.POST, instance=instance)
        if form.is_valid():
            dept = form.save()
            action = "Updated" if instance else "Added"
            messages.success(request, f"{action} department “{dept.name}”.")
            return redirect("admin_panel:department_list")
        edit_obj = instance
        messages.error(request, "Please correct the department name.")
    else:
        form = DepartmentForm(instance=edit_obj)

    departments = Department.objects.annotate(user_count=Count("users")).order_by("name")
    return render(
        request,
        "admin_panel/catalog.html",
        {
            "section": "departments",
            "form": form,
            "edit_obj": edit_obj,
            "departments": departments,
        },
    )


@admin_required
@require_POST
def department_delete(request, dept_id):
    dept = get_object_or_404(Department, pk=dept_id)
    name = dept.name
    dept.delete()
    messages.success(request, f"Deleted department “{name}”.")
    return redirect("admin_panel:department_list")


@admin_required
def type_list(request):
    edit_id = request.GET.get("edit", "").strip()
    edit_obj = get_object_or_404(AppointmentType, pk=int(edit_id)) if edit_id.isdigit() else None

    if request.method == "POST":
        post_edit_id = request.POST.get("edit_id", "").strip()
        instance = (
            get_object_or_404(AppointmentType, pk=int(post_edit_id))
            if post_edit_id.isdigit()
            else None
        )
        form = AppointmentTypeForm(request.POST, instance=instance)
        if form.is_valid():
            atype = form.save()
            action = "Updated" if instance else "Added"
            messages.success(request, f"{action} appointment type “{atype.type_name}”.")
            return redirect("admin_panel:type_list")
        edit_obj = instance
        messages.error(request, "Please correct the appointment type name.")
    else:
        form = AppointmentTypeForm(instance=edit_obj)

    types = AppointmentType.objects.annotate(appt_count=Count("appointment")).order_by("type_name")
    return render(
        request,
        "admin_panel/catalog.html",
        {
            "section": "types",
            "form": form,
            "edit_obj": edit_obj,
            "types": types,
        },
    )


@admin_required
@require_POST
def type_delete(request, type_id):
    atype = get_object_or_404(AppointmentType, pk=type_id)
    name = atype.type_name
    try:
        atype.delete()
        messages.success(request, f"Deleted appointment type “{name}”.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete “{name}” because existing appointments reference it.",
        )
    return redirect("admin_panel:type_list")


# ---- Read-only Audit Logs ----
@admin_required
def audit_logs(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()

    qs = AppointmentLog.objects.select_related(
        "appointment", "appointment__student", "appointment__slot__faculty", "changed_by"
    ).order_by("-changed_at", "-log_id")
    if status_filter in Status.values:
        qs = qs.filter(new_status=status_filter)
    else:
        status_filter = ""
    if query:
        qs = qs.filter(
            Q(appointment__student__full_name__icontains=query)
            | Q(appointment__slot__faculty__full_name__icontains=query)
            | Q(changed_by__full_name__icontains=query)
            | Q(appointment__purpose__icontains=query)
        )

    return render(
        request,
        "admin_panel/audit_logs.html",
        {
            "logs": qs[:100],
            "statuses": Status.choices,
            "query": query,
            "selected_status": status_filter,
        },
    )
