import logging
import time
import uuid
from contextvars import ContextVar

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover
    from pythonjsonlogger.jsonlogger import JsonFormatter

request_id_var: ContextVar[str | None] = ContextVar('request_id', default=None)
user_id_var: ContextVar[int | None] = ContextVar('user_id', default=None)

logger = logging.getLogger('finchat.http')


class RequestContextFilter(logging.Filter):
    """Injects request_id and user_id into every structured log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, 'request_id', None) is None:
            record.request_id = request_id_var.get()
        if getattr(record, 'user_id', None) is None:
            record.user_id = user_id_var.get()
        return True


class StructuredJsonFormatter(JsonFormatter):
    """JSON formatter adding standardized timestamp and context fields."""

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:
        super().add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = self.formatTime(record, self.datefmt)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        if getattr(record, 'request_id', None) and 'request_id' not in log_record:
            log_record['request_id'] = record.request_id
        if getattr(record, 'user_id', None) is not None and 'user_id' not in log_record:
            log_record['user_id'] = record.user_id


class RequestLoggingMiddleware:
    """Assigns a request_id and logs request lifecycle details."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        req_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.request_id = req_id
        token_req = request_id_var.set(req_id)
        token_user = user_id_var.set(getattr(getattr(request, 'user', None), 'id', None))
        start = time.monotonic()

        try:
            response = self.get_response(request)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            user = getattr(request, 'user', None)
            uid = user.id if user and getattr(user, 'is_authenticated', False) else None
            username = user.username if user and getattr(user, 'is_authenticated', False) else None
            user_id_var.set(uid)

            status_code = getattr(locals().get('response', None), 'status_code', 500)
            logger.info(
                'HTTP request processed',
                extra={
                    'method': request.method,
                    'path': request.get_full_path(),
                    'status_code': status_code,
                    'duration_ms': duration_ms,
                    'user_id': uid,
                    'username': username,
                    'remote_addr': self._get_client_ip(request),
                },
            )
            request_id_var.reset(token_req)
            user_id_var.reset(token_user)

        response['X-Request-ID'] = req_id
        if request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private, max-age=0'
            response['Pragma'] = 'no-cache'
            existing_vary = response.get('Vary')
            vary_parts = [v.strip() for v in existing_vary.split(',') if v.strip()] if existing_vary else []
            if 'Authorization' not in vary_parts:
                vary_parts.append('Authorization')
            response['Vary'] = ', '.join(vary_parts)
        return response

    @staticmethod
    def _get_client_ip(request) -> str:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

