import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger('finchat.exceptions')


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    view = context.get('view')
    view_name = view.__class__.__name__ if view else 'UnknownView'
    request = context.get('request')
    user_id = getattr(getattr(request, 'user', None), 'id', None)

    if response is not None:
        logger.warning(
            'API handled exception',
            extra={
                'view': view_name,
                'status_code': response.status_code,
                'user_id': user_id,
                'detail': str(response.data),
            },
        )
        if isinstance(response.data, dict):
            payload = dict(response.data)
            payload.setdefault('status_code', response.status_code)
            if 'detail' not in payload:
                payload['detail'] = 'Request validation failed.'
            response.data = payload
        else:
            response.data = {
                'detail': response.data,
                'status_code': response.status_code,
            }
        return response

    logger.exception(
        'Unhandled API exception',
        extra={
            'view': view_name,
            'user_id': user_id,
        },
    )
    return Response(
        {
            'detail': 'An unexpected internal error occurred.',
            'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

