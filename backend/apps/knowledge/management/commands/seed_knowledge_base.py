import logging
from django.conf import settings
from django.core.management.base import BaseCommand
import httpx

logger = logging.getLogger('finchat.knowledge')


class Command(BaseCommand):
    help = 'Bulk index local banking documents from data/ into Qdrant vector database via ai-service.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Calling AI service to seed local banking documents..."))
        url = f"{settings.AI_SERVICE_URL.rstrip('/')}/knowledge/seed-local"
        headers = {'X-Internal-Key': settings.INTERNAL_API_KEY}

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    docs_count = data.get("indexed_documents_count", 0)
                    chunks_count = data.get("total_chunks_indexed", 0)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully seeded {docs_count} documents ({chunks_count} total chunks) into Qdrant!"
                        )
                    )
                else:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Failed to seed documents. Status: {resp.status_code}, Body: {resp.text}"
                        )
                    )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Connection to AI service failed: {exc}"))
