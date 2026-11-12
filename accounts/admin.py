from django import forms
from django.contrib import admin

from .models import Department, User


class UserAdminForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        help_text="Required for new users. Leave blank to keep the current password.",
    )

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "department", "is_active")

    def clean(self):
        data = super().clean()
        if not self.instance.pk and not data.get("new_password"):
            self.add_error("new_password", "Password is required for new users.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password"):
            user.set_password(self.cleaned_data["new_password"])
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ("email", "full_name", "role", "department", "is_active", "created_at")
    list_filter = ("role", "department", "is_active")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "full_name", "role", "department", "is_active", "new_password")}),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("department_id", "name")
    search_fields = ("name",)
