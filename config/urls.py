from django.contrib import admin
from django.urls import include, path

# Uploaded receipt images are stored in the database and only available to
# their owner through expenses.views.receipt_views.receipt_image.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("expenses.urls")),
]
