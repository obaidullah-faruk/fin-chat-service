import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission


class HasInternalAPIKey(BasePermission):
    """Allows access only to internal callers presenting a valid X-Internal-Key header."""

    message = 'Internal access only.'

    def has_permission(self, request, view) -> bool:
        expected_key = getattr(settings, 'INTERNAL_API_KEY', '') or ''
        provided_key = request.headers.get('X-Internal-Key')
        if not expected_key or not provided_key:
            return False
        return secrets.compare_digest(provided_key, expected_key)


def get_internal_user(request):
    """Resolve and return the active user referenced by the X-User-Id header."""
    raw_user_id = request.headers.get('X-User-Id')
    if raw_user_id is None or not str(raw_user_id).strip():
        raise ValidationError({'detail': 'Missing X-User-Id header.'})

    try:
        user_id = int(str(raw_user_id).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError({'detail': 'Invalid X-User-Id header; must be a positive integer.'}) from exc

    if user_id <= 0:
        raise ValidationError({'detail': 'Invalid X-User-Id header; must be a positive integer.'})

    User = get_user_model()
    try:
        return User.objects.select_related('role').get(pk=user_id, is_active=True)
    except User.DoesNotExist as exc:
        raise NotFound('Active user not found.') from exc

