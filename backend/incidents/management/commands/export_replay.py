from django.core.management.base import BaseCommand, CommandError

from incidents.models import Incident
from incidents.replay import RECORDING, export_incident


class Command(BaseCommand):
    help = "Save a finished incident as the replay recording used by replay mode (FR-9.2)."

    def add_arguments(self, parser):
        parser.add_argument("incident_id")

    def handle(self, *args, incident_id, **options):
        try:
            incident = Incident.objects.get(pk=incident_id)
        except Incident.DoesNotExist as exc:
            raise CommandError(f"no incident {incident_id}") from exc
        if incident.status not in ("READY_TO_MERGE", "RESOLVED"):
            raise CommandError(f"{incident_id} is {incident.status}; record a successful run")
        path = export_incident(incident, RECORDING)
        self.stdout.write(f"recorded {incident_id} -> {path}")
