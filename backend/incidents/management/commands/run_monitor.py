from django.core.management.base import BaseCommand

from incidents.monitor import AlertMonitor


class Command(BaseCommand):
    help = "Run the Alert Monitor in the foreground (alternative to the in-server monitor thread)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="take a single sample and exit")
        parser.add_argument("--no-incidents", action="store_true", help="sample only; never open incidents")

    def handle(self, *args, once, no_incidents, **options):
        monitor = AlertMonitor(start_incidents=not no_incidents)
        if once:
            snap = monitor.tick()
            self.stdout.write(str(snap) if snap else f"telemetry unavailable: {monitor.last_error}")
            return
        monitor.run_forever()
