#!/usr/bin/env python3
"""
Headless end-to-end demo against a running stack (backend + docker compose).

    python scripts/demo.py                 # traffic -> incident -> fix -> PR -> ready to merge
    python scripts/demo.py --conflict      # + a teammate pushes a conflicting change; watch the loop repair it
    python scripts/demo.py --conflict --merge   # + merge as the human reviewer at the end (local provider)

Only uses the public API, exactly like the dashboard.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000/api/v1"


def call(path, method="GET", body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body or {}).encode() if method != "GET" else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["data"]
    except urllib.error.HTTPError as exc:
        err = json.loads(exc.read()).get("error", {})
        sys.exit(f"API error {exc.code}: {err.get('code')}: {err.get('message')}")
    except urllib.error.URLError:
        sys.exit(f"Backend not reachable at {API}. Start it with: python scripts/dev.py")


def wait_for_status(incident_id, wanted, seen, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        inc = call(f"/incidents/{incident_id}")
        for e in inc["timeline"]:
            if e["id"] not in seen:
                seen.add(e["id"])
                print(f"{e['ts'][11:19]} [{e['tag']:<8}] {e['message']}")
        if inc["status"] in wanted:
            return inc
        if inc["status"] == "ESCALATED":
            sys.exit(f"\nESCALATED: {inc['escalation_reason']}")
        time.sleep(1)
    sys.exit("timed out")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conflict", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    system = call("/system")
    print(f"mode={system['mode']} sandbox={system['sandbox']['engine']} (isolated={system['sandbox']['isolated']}) "
          f"delivery={system['delivery']['provider']} db_reachable={system['database']['reachable']}")
    if not system["database"]["reachable"]:
        sys.exit("PostgreSQL is not reachable: docker compose up -d --build")

    print("\n-> resetting environment")
    call("/demo/reset", "POST", {"clear_incidents": True, "reseed_repo": True})
    print("-> sending traffic to the victim service (the monitor will raise the alert by itself)")
    call("/demo/trigger", "POST")

    started = time.time()
    while True:
        incidents = call("/incidents")
        if incidents:
            break
        traffic = call("/demo/traffic")
        print(f"   traffic: sent {traffic['sent']} ok {traffic['ok']} errors {traffic['errors']}", end="\r")
        if time.time() - started > 180:
            sys.exit("\nno incident after 3 minutes - is the victim leaking? check docker compose logs victim_service")
        time.sleep(1)
    incident_id = incidents[0]["id"]
    print(f"\n-> incident {incident_id} opened\n")

    seen = set()
    inc = wait_for_status(incident_id, {"READY_TO_MERGE", "RESOLVED"}, seen)
    print(f"\nREADY TO MERGE after {inc['mttr_seconds']}s (service restored after {inc['time_to_mitigate_seconds']}s)")

    if args.conflict:
        print("\n-> a teammate pushes a conflicting change to main")
        call("/demo/teammate-push", "POST")
        wait_for_status(incident_id, {"UPDATING_PR"}, seen)
        inc = wait_for_status(incident_id, {"READY_TO_MERGE"}, seen)
        print(f"\nconflict repaired; PR ready again (repair rounds: {inc['pull_request'].get('rounds')})")

    if args.merge:
        print("\n-> merging as the human reviewer")
        call(f"/incidents/{incident_id}/merge", "POST")
        wait_for_status(incident_id, {"RESOLVED"}, seen)
        print("\nRESOLVED")


if __name__ == "__main__":
    main()
