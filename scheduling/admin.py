from django.contrib import admin, messages

from . import services
from .models import Appointment, AppointmentLog, AppointmentType, Status, TimeSlot


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("slot_id", "faculty", "slot_date", "start_time", "end_time")
    list_filter = ("slot_date", "faculty__department")
    search_fields = ("faculty__full_name", "faculty__email")


@admin.register(AppointmentType)
class AppointmentTypeAdmin(admin.ModelAdmin):
    list_display = ("type_id", "type_name")


class LogInline(admin.TabularInline):
    model = AppointmentLog
    extra = 0
    can_delete = False
    readonly_fields = ("changed_by", "old_status", "new_status", "changed_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("appointment_id", "student", "slot", "type", "status", "created_at")
    list_filter = ("status", "type")
    search_fields = ("student__full_name", "student__email", "slot__faculty__full_name")
    readonly_fields = ("status", "created_at", "updated_at")
    inlines = [LogInline]
    actions = ["approve", "cancel", "complete"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:  # log creation so history stays complete
            AppointmentLog.objects.create(
                appointment=obj, changed_by=request.user, old_status=None, new_status=obj.status
            )

    def _apply(self, request, queryset, status):
        for appt in queryset:
            try:
                services.change_status(appt, status, request.user)
            except services.BusinessRuleError as e:
                self.message_user(request, f"#{appt.pk}: {e}", level=messages.ERROR)

    @admin.action(description="Approve selected appointments")
    def approve(self, request, queryset):
        self._apply(request, queryset, Status.APPROVED)

    @admin.action(description="Cancel selected appointments")
    def cancel(self, request, queryset):
        self._apply(request, queryset, Status.CANCELLED)

    @admin.action(description="Mark selected appointments completed")
    def complete(self, request, queryset):
        self._apply(request, queryset, Status.COMPLETED)


@admin.register(AppointmentLog)
class AppointmentLogAdmin(admin.ModelAdmin):
    list_display = ("log_id", "appointment", "changed_by", "old_status", "new_status", "changed_at")
    list_filter = ("new_status",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
