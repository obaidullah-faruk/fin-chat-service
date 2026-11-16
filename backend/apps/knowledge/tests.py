from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import httpx
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_SUPERADMIN

User = get_user_model()


class KnowledgeAPITests(APITestCase):
    def setUp(self):
        self.superadmin_role = Role.objects.create(name=ROLE_SUPERADMIN)
        self.admin_role = Role.objects.create(name=ROLE_ADMIN)
        self.manager_role = Role.objects.create(name=ROLE_MANAGER)
        self.customer_role = Role.objects.create(name=ROLE_CUSTOMER)

        self.superadmin = User.objects.create_user(
            username='test_superadmin',
            email='superadmin@test.local',
            password='Password123!',
            role=self.superadmin_role,
        )
        self.admin_user = User.objects.create_user(
            username='test_admin',
            email='admin@test.local',
            password='Password123!',
            role=self.admin_role,
        )
        self.manager_user = User.objects.create_user(
            username='test_manager',
            email='manager@test.local',
            password='Password123!',
            role=self.manager_role,
        )
        self.customer_user = User.objects.create_user(
            username='test_customer',
            email='customer@test.local',
            password='Password123!',
            role=self.customer_role,
        )

        self.list_url = reverse('knowledge-list')
        self.upload_url = reverse('knowledge-upload')
        self.seed_url = reverse('knowledge-seed-local')

    def test_anonymous_access_denied(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_access_forbidden(self):
        self.client.force_authenticate(user=self.customer_user)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_access_forbidden(self):
        self.client.force_authenticate(user=self.manager_user)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.knowledge.views._call_ai_service')
    def test_admin_list_documents(self, mock_call):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "doc_id": "rates_1",
                "title": "Deposit Rates",
                "filename": "rates.md",
                "category": "rates",
                "version": 1,
                "chunk_count": 5,
            }
        ]
        mock_call.return_value = mock_resp

        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["doc_id"], "rates_1")

    @patch('apps.knowledge.views._call_ai_service')
    def test_upload_document_success(self, mock_call):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "success", "doc_id": "test_doc", "chunk_count": 3}'
        mock_resp.json.return_value = {"status": "success", "doc_id": "test_doc", "chunk_count": 3}
        mock_call.return_value = mock_resp

        self.client.force_authenticate(user=self.admin_user)
        file = SimpleUploadedFile("test.txt", b"Hello banking text", content_type="text/plain")
        resp = self.client.post(
            self.upload_url,
            {"file": file, "title": "Test Title", "category": "policy"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["doc_id"], "test_doc")

    @patch('apps.knowledge.views._call_ai_service')
    def test_upload_document_content_collision_409(self, mock_call):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "collision", "message": "Duplicate text"}'
        mock_resp.json.return_value = {"status": "collision", "message": "Duplicate text"}
        mock_call.return_value = mock_resp

        self.client.force_authenticate(user=self.superadmin)
        file = SimpleUploadedFile("duplicate.txt", b"Same content", content_type="text/plain")
        resp = self.client.post(
            self.upload_url,
            {"file": file, "title": "Duplicate", "category": "rates"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.json()["status"], "collision")
