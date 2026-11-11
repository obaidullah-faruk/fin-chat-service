import logging
from typing import Any

from .models import ActivityLog

logger = logging.getLogger('finchat.audit')


def get_client_ip(request) -> str | None:
    if request is None:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def record_activity(
    *,
    subject_user,
    category: str,
    action: str,
    description: str,
    actor=None,
    request=None,
    metadata: dict[str, Any] | None = None,
) -> ActivityLog | None:
    if actor is None and request is not None and getattr(request, 'user', None) and request.user.is_authenticated:
        actor = request.user
    try:
        return ActivityLog.objects.create(
            actor=actor,
            subject_user=subject_user,
            category=category,
            action=action,
            description=description,
            metadata=metadata or {},
            ip_address=get_client_ip(request),
        )
    except Exception:
        logger.exception(
            'Failed to persist activity log',
            extra={'action': action, 'subject_user_id': getattr(subject_user, 'id', None)},
        )
        return None

