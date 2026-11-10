from django.contrib import admin
from django.urls import include, path

from config import views

admin.site.site_header = "AppointED Admin"
admin.site.site_title = "AppointED Admin"
admin.site.index_title = "Manage users, slots and appointments"

handler403 = "config.views.permission_denied"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("theme/", views.set_theme, name="set_theme"),
    path("accounts/", include("accounts.urls")),
    path("", include("scheduling.urls")),
]
