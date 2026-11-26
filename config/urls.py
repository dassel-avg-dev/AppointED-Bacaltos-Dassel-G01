from django.contrib import admin
from django.urls import include, path

from config import views

admin.site.site_header = "AppointED Admin"
admin.site.site_title = "AppointED Admin"
admin.site.index_title = "Manage users, slots and appointments"
admin.site.site_url = "/panel/"

handler403 = "config.views.permission_denied"
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("panel/", include("admin_panel.urls")),
    path("theme/", views.set_theme, name="set_theme"),
    path("accounts/", include("accounts.urls")),
    path("", include("scheduling.urls")),
]
