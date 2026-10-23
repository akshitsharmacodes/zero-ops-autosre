import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import UserActivity

PAGES = ["/home", "/pricing", "/docs", "/blog", "/signup", "/dashboard"]


class Command(BaseCommand):
    help = "Insert deterministic sample activity rows (only when the table is empty)."

    def add_arguments(self, parser):
        parser.add_argument("--rows", type=int, default=500)

    def handle(self, *args, rows, **options):
        if UserActivity.objects.exists():
            self.stdout.write("activity already seeded")
            return
        rng = random.Random(42)
        now = timezone.now()
        UserActivity.objects.bulk_create(
            UserActivity(
                user_id=rng.randint(100, 160),
                page=rng.choice(PAGES),
                event=rng.choice(["view", "view", "view", "click"]),
                created_at=now - timedelta(minutes=rng.randint(0, 60 * 24)),
            )
            for _ in range(rows)
        )
        self.stdout.write(f"seeded {rows} activity rows")
