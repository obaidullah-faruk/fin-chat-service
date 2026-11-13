import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_http_application = get_asgi_application()


async def application(scope, receive, send):
    """
    Root ASGI application routing HTTP requests to Django and
    WebSocket connections to the FinChat streaming WebSocket consumer.
    """
    scope_type = scope.get('type')
    if scope_type == 'http':
        await django_http_application(scope, receive, send)
    elif scope_type == 'websocket':
        from apps.chat.websocket import chat_websocket_application
        await chat_websocket_application(scope, receive, send)
    elif scope_type == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            elif message['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    else:
        raise NotImplementedError(f"Unsupported ASGI scope type: {scope_type}")
