from django.db import models

class UserMetric(models.Model):
    user_id = models.IntegerField()
    action = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"UserMetric({self.user_id}, {self.action})"
