from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Department, User


class TailwindFormMixin:
    """Attach the shared .input class to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            attrs = field.widget.attrs
            attrs["class"] = (attrs.get("class", "") + " input").strip()
            attrs.setdefault("placeholder", field.label or name)


class RegistrationForm(TailwindFormMixin, UserCreationForm):
    role = forms.ChoiceField(
        choices=[(User.Role.STUDENT, "Student"), (User.Role.FACULTY, "Faculty")]
    )
    department = forms.ModelChoiceField(queryset=Department.objects.all())

    class Meta:
        model = User
        fields = ("email", "full_name", "role", "department")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data["role"]
        user.department = self.cleaned_data["department"]
        if commit:
            user.save()
        return user


class ProfileForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "email", "department")


class EmailAuthenticationForm(TailwindFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))
