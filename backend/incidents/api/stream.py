"""
Live timeline over Server-Sent Events (FR-8.2, NFR-P2 < 1s per event).

Events are read from the database (not an in-memory queue), so the stream survives
reconnects (`Last-Event-ID`), works across processes, and nothing is ever lost.
"""
import asyncio
import json

from django.http import JsonResponse, StreamingHttpResponse

from ..models import FINAL_STATUSES, Incident, TimelineEvent

POLL_SECONDS = 0.4
KEEPALIVE_EVERY = 25  # polls


async def incident_stream(request, incident_id):
    if not await Incident.objects.filter(pk=incident_id).aexists():
        return JsonResponse({"data": None, "error": {"code": "NOT_FOUND", "message": "Incident not found"}}, status=404)
    try:
        last_id = int(request.headers.get("Last-Event-ID") or request.GET.get("after") or 0)
    except ValueError:
        last_id = 0

    async def events():
        nonlocal last_id
        last_status, idle = None, 0
        yield "retry: 2000\n\n"
        while True:
            batch = [e async for e in TimelineEvent.objects.filter(incident_id=incident_id, id__gt=last_id)
                     .order_by("id").values("id", "ts", "tag", "message", "state")[:200]]
            for e in batch:
                last_id = e["id"]
                payload = {**e, "ts": e["ts"].isoformat()}
                yield f"id: {e['id']}\nevent: timeline\ndata: {json.dumps(payload)}\n\n"
            status = await Incident.objects.filter(pk=incident_id).values_list("status", flat=True).afirst()
            if status != last_status:
                last_status = status
                yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
            if status in FINAL_STATUSES and not batch:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0 if batch else idle + 1
            if idle and idle % KEEPALIVE_EVERY == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(POLL_SECONDS)

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
