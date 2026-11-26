from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.overview, name="overview"),
    # Users
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:user_id>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:user_id>/toggle/", views.user_toggle_active, name="user_toggle_active"),
    # Appointments
    path("appointments/", views.appointment_list, name="appointment_list"),
    path("appointments/<int:appointment_id>/", views.appointment_detail, name="appointment_detail"),
    path("appointments/<int:appointment_id>/status/", views.appointment_status, name="appointment_status"),
    # Time slots
    path("slots/", views.slot_list, name="slot_list"),
    path("slots/new/", views.slot_create, name="slot_create"),
    path("slots/<int:slot_id>/edit/", views.slot_edit, name="slot_edit"),
    path("slots/<int:slot_id>/delete/", views.slot_delete, name="slot_delete"),
    # Catalog: Departments & Appointment Types
    path("departments/", views.department_list, name="department_list"),
    path("departments/<int:dept_id>/delete/", views.department_delete, name="department_delete"),
    path("appointment-types/", views.type_list, name="type_list"),
    path("appointment-types/<int:type_id>/delete/", views.type_delete, name="type_delete"),
    # Read-only Audit Logs
    path("logs/", views.audit_logs, name="audit_logs"),
]
