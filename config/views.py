from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

THEME_MAX_AGE = 60 * 60 * 24 * 365


@require_POST
def set_theme(request):
    chosen = "dark" if request.POST.get("theme") == "dark" else "light"
    nxt = request.POST.get("next", "")
    if not (nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})):
        nxt = "/"
    response = redirect(nxt)
    response.set_cookie("theme", chosen, max_age=THEME_MAX_AGE, samesite="Lax")
    return response


def permission_denied(request, exception=None):
    return render(request, "403.html", status=403)
