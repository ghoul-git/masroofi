from django.contrib import admin
from django.urls import include, path

# Uploaded receipt images are not served from MEDIA_URL: they are only
# available to their owner through expenses.views.receipt_views.receipt_image.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("expenses.urls")),
]
