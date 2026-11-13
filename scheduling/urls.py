from django.urls import path

from . import views

app_name = "scheduling"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("faculty/slots/", views.slot_list, name="slot_list"),
    path("faculty/slots/new/", views.slot_create, name="slot_create"),
    path("faculty/slots/<int:slot_id>/delete/", views.slot_delete, name="slot_delete"),
    path("faculty-directory/", views.faculty_directory, name="faculty_directory"),
    path("faculty-directory/<int:user_id>/", views.faculty_slots, name="faculty_slots"),
    path("slots/<int:slot_id>/book/", views.book, name="book"),
    path("appointments/", views.appointment_list, name="appointment_list"),
    path("appointments/<int:appointment_id>/", views.appointment_detail, name="appointment_detail"),
    path("appointments/<int:appointment_id>/status/", views.appointment_status, name="appointment_status"),
]
