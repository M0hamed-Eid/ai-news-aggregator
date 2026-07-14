from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.behavior.models import UserEvent

RETENTION_DAYS = 90


class Command(BaseCommand):
    help = "Delete UserEvent rows older than the retention window (default 90 days)."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        deleted, _ = UserEvent.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Pruned {deleted} user_events row(s) older than {RETENTION_DAYS} days")
