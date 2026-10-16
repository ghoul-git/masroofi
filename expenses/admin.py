from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models.functions import Length

from expenses.models import Category, ChatMessage, Expense, Item, Receipt, User

admin.site.register(User, UserAdmin)
admin.site.register(Category)
admin.site.register(Expense)
admin.site.register(Item)
admin.site.register(ChatMessage)


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    """The image is never loaded or shown here, on the list or the detail page; the detail
    page shows only its size, which the database computes."""

    list_display = ("id", "user", "status", "uploaded_at")
    list_filter = ("status",)
    exclude = ("image_data",)
    readonly_fields = ("image_size",)

    def get_queryset(self, request):
        return super().get_queryset(request).defer("image_data").annotate(image_bytes=Length("image_data"))

    @admin.display(description="Image")
    def image_size(self, receipt):
        size = getattr(receipt, "image_bytes", None)
        if not size:
            return "No image stored"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"
