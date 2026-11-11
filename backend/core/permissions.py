from rest_framework.permissions import BasePermission

ROLE_SUPERADMIN = 'superadmin'
ROLE_ADMIN = 'admin'
ROLE_MANAGER = 'manager'
ROLE_CUSTOMER = 'customer'

ALL_ROLES = (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER, ROLE_CUSTOMER)

ROLE_HIERARCHY = {
    ROLE_SUPERADMIN: 4,
    ROLE_ADMIN: 3,
    ROLE_MANAGER: 2,
    ROLE_CUSTOMER: 1,
}


def get_user_role(user) -> str | None:
    if not user or not user.is_authenticated:
        return None
    role = getattr(user, 'role', None)
    return role.name if role else None


class HasRole(BasePermission):
    """Checks `view.allowed_roles` if defined on the view."""

    message = 'You do not have the required role to perform this action.'

    def has_permission(self, request, view):
        role_name = get_user_role(request.user)
        if not role_name:
            return False
        allowed_roles = getattr(view, 'allowed_roles', None)
        if allowed_roles is None:
            return True
        return role_name in allowed_roles


class IsSuperAdmin(BasePermission):
    message = 'Superadmin access required.'

    def has_permission(self, request, view):
        return get_user_role(request.user) == ROLE_SUPERADMIN


class IsAdminOrAbove(BasePermission):
    message = 'Admin or Superadmin access required.'

    def has_permission(self, request, view):
        return get_user_role(request.user) in (ROLE_SUPERADMIN, ROLE_ADMIN)


class IsManagerOrAbove(BasePermission):
    message = 'Manager, Admin, or Superadmin access required.'

    def has_permission(self, request, view):
        return get_user_role(request.user) in (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MANAGER)


class IsCustomerOrAbove(BasePermission):
    message = 'Authenticated role required.'

    def has_permission(self, request, view):
        return get_user_role(request.user) in ALL_ROLES


class IsOwnerOrAdmin(BasePermission):
    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        role_name = get_user_role(request.user)
        if role_name in (ROLE_SUPERADMIN, ROLE_ADMIN):
            return True
        owner = getattr(obj, 'user', None) or getattr(obj, 'requester', None)
        if owner is not None:
            return owner == request.user
        return obj == request.user

