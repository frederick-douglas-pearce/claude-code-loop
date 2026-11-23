"""Budget kill-switch Cloud Function (E8-S7, #101 / D034).

Cloud Run has **no native hard cost cap** — ``--max-instances`` bounds concurrency, not
spend. This function is the backstop: a GCP **Billing Budget** publishes to a Pub/Sub
topic as spend crosses alert thresholds; this function receives that message and, once
spend reaches a configured fraction of the budget, **pauses the service** by setting
``max_instance_count = 0`` (Cloud Run then serves nothing and bills nothing).

Deploy (2nd-gen, Pub/Sub-triggered) — see ``deploy/killswitch/README.md``. It is
**optional but recommended**: at this project's free-tier traffic it should never fire;
it exists so a runaway bill is structurally impossible, not merely unlikely.

Env: ``GCP_PROJECT``, ``CLOUD_RUN_REGION``, ``CLOUD_RUN_SERVICE``, and optional
``PAUSE_AT_FRACTION`` (default ``1.0`` = pause at 100% of the budget).
"""

from __future__ import annotations

import base64
import json
import os

import functions_framework
from cloudevents.http import CloudEvent
from google.cloud import run_v2


@functions_framework.cloud_event
def budget_killswitch(cloud_event: CloudEvent) -> None:
    """Pause the Cloud Run service when billing spend crosses the threshold."""
    project = os.environ["GCP_PROJECT"]
    region = os.environ["CLOUD_RUN_REGION"]
    service_id = os.environ["CLOUD_RUN_SERVICE"]
    pause_at = float(os.environ.get("PAUSE_AT_FRACTION", "1.0"))

    payload = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    cost = float(payload.get("costAmount", 0))
    budget = float(payload.get("budgetAmount", 0))

    if budget <= 0 or cost < budget * pause_at:
        print(f"under threshold: cost={cost} budget={budget} frac={pause_at}; no-op")
        return

    client = run_v2.ServicesClient()
    name = client.service_path(project, region, service_id)
    service = client.get_service(name=name)
    if service.template.scaling.max_instance_count == 0:
        print(f"{service_id} already paused (max_instance_count=0); no-op")
        return
    service.template.scaling.max_instance_count = 0
    client.update_service(service=service)
    print(f"PAUSED {service_id}: cost={cost} >= {pause_at:.0%} of budget={budget}")
