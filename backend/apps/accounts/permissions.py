from rest_framework.permissions import BasePermission

from core.permissions import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_SUPERADMIN,
    HasRole,
    get_user_role,
)


class IsOwner(BasePermission):
    message = 'You may only access your own records.'

    def has_object_permission(self, request, view, obj):
        if get_user_role(request.user) in (ROLE_SUPERADMIN, ROLE_ADMIN):
            return True
        owner = getattr(obj, 'user', obj)
        return owner == request.user


class CanManageUser(BasePermission):
    message = 'You do not have permission to manage this user.'

    def has_permission(self, request, view):
        return get_user_role(request.user) in (ROLE_SUPERADMIN, ROLE_ADMIN)

    def has_object_permission(self, request, view, obj):
        actor_role = get_user_role(request.user)
        if actor_role == ROLE_SUPERADMIN:
            return True
        if actor_role == ROLE_ADMIN:
            target_role = get_user_role(obj)
            if target_role in (ROLE_CUSTOMER, ROLE_MANAGER):
                return True
            return obj.created_by_id == request.user.id
        return False


__all__ = ['HasRole', 'IsOwner', 'CanManageUser']

