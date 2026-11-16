import base64
import logging

from django.conf import settings
import httpx
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdminOrAbove

logger = logging.getLogger('finchat.knowledge')


class AIServiceUnavailableError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'AI knowledge service is temporarily unavailable.'
    default_code = 'ai_service_unavailable'


def _call_ai_service(method: str, path: str, json_data: dict | None = None) -> httpx.Response:
    url = f"{settings.AI_SERVICE_URL.rstrip('/')}{path}"
    headers = {'X-Internal-Key': settings.INTERNAL_API_KEY}
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.request(method, url, json=json_data, headers=headers)
            return resp
    except httpx.HTTPError as exc:
        logger.error("Failed connecting to AI service at %s: %s", url, exc)
        raise AIServiceUnavailableError() from exc


class KnowledgeDocumentListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAbove]

    def get(self, request):
        """List all documents currently indexed in Qdrant."""
        resp = _call_ai_service('GET', '/knowledge/documents')
        if resp.status_code != 200:
            return Response(resp.json() if resp.content else {}, status=resp.status_code)
        return Response(resp.json())


class KnowledgeDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAbove]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """Upload and ingest a document into Qdrant with content collision detection."""
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'detail': 'No file was provided.'}, status=status.HTTP_400_BAD_REQUEST)

        title = request.data.get('title') or uploaded_file.name
        category = request.data.get('category', 'general')
        collision_action = request.data.get('collision_action', 'check')

        file_bytes = uploaded_file.read()
        b64_content = base64.b64encode(file_bytes).decode('utf-8')

        payload = {
            'title': title,
            'filename': uploaded_file.name,
            'category': category,
            'content_base64': b64_content,
            'uploaded_by': request.user.username,
            'collision_action': collision_action,
        }

        resp = _call_ai_service('POST', '/knowledge/ingest', json_data=payload)
        data = resp.json() if resp.content else {}

        if resp.status_code != 200:
            return Response(data, status=resp.status_code)

        if data.get('status') == 'collision':
            return Response(data, status=status.HTTP_409_CONFLICT)

        logger.info(
            "Document uploaded to knowledge base",
            extra={'user': request.user.username, 'filename': uploaded_file.name, 'doc_id': data.get('doc_id')},
        )
        return Response(data, status=status.HTTP_201_CREATED)


class KnowledgeDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAbove]

    def delete(self, request, doc_id: str):
        """Purge document and all its vector chunks from Qdrant."""
        resp = _call_ai_service('DELETE', f'/knowledge/documents/{doc_id}')
        if resp.status_code not in (200, 204):
            return Response(resp.json() if resp.content else {}, status=resp.status_code)
        logger.info(
            "Document deleted from knowledge base",
            extra={'user': request.user.username, 'doc_id': doc_id},
        )
        return Response({'status': 'deleted', 'doc_id': doc_id}, status=status.HTTP_200_OK)


class KnowledgeLocalSeedView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAbove]

    def post(self, request):
        """Bulk seed all bank documents from local data/ directory into Qdrant."""
        resp = _call_ai_service('POST', '/knowledge/seed-local')
        data = resp.json() if resp.content else {}
        if resp.status_code != 200:
            return Response(data, status=resp.status_code)
        logger.info(
            "Local knowledge data bulk seeded",
            extra={
                'user': request.user.username,
                'count': data.get('indexed_documents_count'),
                'chunks': data.get('total_chunks_indexed'),
            },
        )
        return Response(data, status=status.HTTP_200_OK)
