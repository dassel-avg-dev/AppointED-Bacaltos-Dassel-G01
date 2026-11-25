import datetime

from django import forms
from django.utils import timezone

from accounts.forms import TailwindFormMixin

from .models import AppointmentType


class TimeSlotForm(TailwindFormMixin, forms.Form):
    slot_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(label="Start time", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="End time", widget=forms.TimeInput(attrs={"type": "time"}))

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


class BookingForm(TailwindFormMixin, forms.Form):
    type = forms.ModelChoiceField(queryset=AppointmentType.objects.all(), label="Appointment type")
    purpose = forms.CharField(
        max_length=255,
        help_text="Briefly explain why you are booking (up to 255 characters).",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_purpose(self):
        purpose = self.cleaned_data["purpose"].strip()
        if not purpose:
            raise forms.ValidationError("A purpose is required.")
        return purpose
