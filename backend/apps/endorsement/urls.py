from django.urls import path

from .views import EndorsementListCreateView, EndorsementReviewView

urlpatterns = [
    path('', EndorsementListCreateView.as_view(), name='endorsement-list-create'),
    path('<int:pk>/review/', EndorsementReviewView.as_view(), name='endorsement-review'),
]

