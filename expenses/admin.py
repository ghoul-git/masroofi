from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from expenses.models import Category, ChatMessage, Expense, Item, Receipt, User

admin.site.register(User, UserAdmin)
admin.site.register(Category)
admin.site.register(Receipt)
admin.site.register(Expense)
admin.site.register(Item)
admin.site.register(ChatMessage)