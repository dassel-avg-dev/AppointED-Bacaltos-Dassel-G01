from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import EmailAuthenticationForm, RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect("scheduling:dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account was created successfully.")
        return redirect("scheduling:dashboard")
    return render(request, "accounts/register.html", {"form": form})


class AppLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, "You are now logged in.")
        return super().form_valid(form)


class AppLogoutView(LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.success(request, "You have been logged out.")
        return response
