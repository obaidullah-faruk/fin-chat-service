from django.urls import path

from .views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentListView,
    KnowledgeDocumentUploadView,
    KnowledgeLocalSeedView,
)

urlpatterns = [
    path('', KnowledgeDocumentListView.as_view(), name='knowledge-list'),
    path('upload/', KnowledgeDocumentUploadView.as_view(), name='knowledge-upload'),
    path('seed-local/', KnowledgeLocalSeedView.as_view(), name='knowledge-seed-local'),
    path('<str:doc_id>/', KnowledgeDocumentDetailView.as_view(), name='knowledge-detail'),
]
