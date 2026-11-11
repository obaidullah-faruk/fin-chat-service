from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ActivityLog, Address, CustomUser, Role, UserProfile


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('id', 'username', 'email', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Role & Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'national_id', 'date_of_birth', 'updated_at')


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'label', 'city', 'country', 'is_primary')
    list_filter = ('label', 'is_primary', 'country')


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'category', 'actor', 'subject_user', 'ip_address', 'created_at')
    list_filter = ('category', 'action', 'created_at')
    search_fields = ('action', 'description', 'actor__username', 'subject_user__username')

