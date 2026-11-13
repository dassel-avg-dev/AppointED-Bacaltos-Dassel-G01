from django import forms

from accounts.forms import TailwindFormMixin

from .models import AppointmentType


class TimeSlotForm(TailwindFormMixin, forms.Form):
    slot_date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(label="Start time", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="End time", widget=forms.TimeInput(attrs={"type": "time"}))


class BookingForm(TailwindFormMixin, forms.Form):
    type = forms.ModelChoiceField(queryset=AppointmentType.objects.all(), label="Appointment type")
    purpose = forms.CharField(
        max_length=255,
        help_text="Briefly explain why you are booking (up to 255 characters).",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
