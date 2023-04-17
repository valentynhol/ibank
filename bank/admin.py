from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Card, BankAccount, User, ExchangeRate, Transaction
from django.utils.translation import gettext_lazy as _


class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'patronymic', 'phone_number')}),
        (_('Permissions'), {
            'fields': ('is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'password_reset_request_time', 'last_operation_confirmation_time')}),
        (_('Перевірка'), {'fields': ('is_active', 'verification_code', 'password_reset_code')}),
        (_('Інші'), {'fields': ('two_step_login', 'second_step_code', 'confirm_operations')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )

    list_display = ('email', 'first_name', 'last_name', 'patronymic', 'phone_number', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'groups')
    search_fields = ('email', 'first_name', 'last_name', 'patronymic', 'phone_number')
    ordering = ('email',)
    readonly_fields = ["date_joined"]


admin.site.register(User, UserAdmin)
admin.site.register(Card)
admin.site.register(BankAccount)
admin.site.register(ExchangeRate)
admin.site.register(Transaction)
