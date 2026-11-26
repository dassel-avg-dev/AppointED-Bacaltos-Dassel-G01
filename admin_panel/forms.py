import datetime

from django import forms
from django.utils import timezone

from accounts.forms import TailwindFormMixin
from accounts.models import Department, User
from scheduling.models import AppointmentType


class AdminUserForm(TailwindFormMixin, forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Required for new users. Leave blank to keep the current password.",
    )

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "department", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].widget.attrs.pop("class", None)
        self.fields["department"].required = False

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("Full name is required.")
        return full_name

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("new_password"):
            self.add_error("new_password", "Password is required for new users.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password"):
            user.set_password(self.cleaned_data["new_password"])
        if commit:
            user.save()
        return user


class AdminTimeSlotForm(TailwindFormMixin, forms.Form):
    faculty = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Faculty member",
    )
    slot_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(label="Start time", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="End time", widget=forms.TimeInput(attrs={"type": "time"}))

    def __init__(self, *args, is_edit=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faculty"].queryset = (
            User.objects.filter(role=User.Role.FACULTY, is_active=True)
            .select_related("department")
            .order_by("full_name")
        )
        if is_edit:
            self.fields["faculty"].disabled = True

    def clean(self):
        cleaned = super().clean()
        slot_date = cleaned.get("slot_date")
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        if slot_date and start_time and end_time:
            if end_time <= start_time:
                raise forms.ValidationError("End time must be later than start time.")
            start_dt = timezone.make_aware(datetime.datetime.combine(slot_date, start_time))
            if start_dt <= timezone.now():
                raise forms.ValidationError("Time slots cannot be scheduled in the past.")
        return cleaned


class DepartmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name",)
        labels = {"name": "Department name"}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Department name is required.")
        qs = Department.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A department with this name already exists.")
        return name


class AppointmentTypeForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = AppointmentType
        fields = ("type_name",)
        labels = {"type_name": "Appointment type name"}

    def clean_type_name(self):
        name = self.cleaned_data["type_name"].strip()
        if not name:
            raise forms.ValidationError("Appointment type name is required.")
        qs = AppointmentType.objects.filter(type_name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("An appointment type with this name already exists.")
        return name
