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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("Full name is required.")
        return full_name

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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("Full name is required.")
        return full_name


class EmailAuthenticationForm(TailwindFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
