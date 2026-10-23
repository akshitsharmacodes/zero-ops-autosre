from django.db import models
from django.utils import timezone


class UserActivity(models.Model):
    user_id = models.IntegerField(db_index=True)
    page = models.CharField(max_length=128)
    event = models.CharField(max_length=32, default="view")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self):
        return f"{self.user_id} {self.event} {self.page}"
