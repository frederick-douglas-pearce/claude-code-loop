# Budget kill-switch (optional)

A tiny Cloud Function that **pauses** the Cloud Run API when billing spend crosses a
threshold — the hard cost cap Cloud Run does not provide natively ([D034](../../.claude/specs/decisions.md)).
It's a backstop; at free-tier traffic it should never fire.

**Flow:** GCP Billing Budget → Pub/Sub topic → this function → sets the service's
`max_instance_count = 0` (serves nothing, bills nothing) once spend ≥ `PAUSE_AT_FRACTION`
of the budget. Un-pause by redeploying (`.github/workflows/deploy.yml` re-sets
`--max-instances=1`) after resolving the cause.

## Deploy

```
PROJECT=uspv-api ; REGION=us-west1 ; SERVICE=usvote-api

# 1. Pub/Sub topic the budget publishes to.
gcloud pubsub topics create budget-alerts

# 2. The function (2nd-gen, Pub/Sub-triggered). Its runtime SA needs run.admin on the service.
gcloud functions deploy budget-killswitch \
  --gen2 --runtime=python312 --region="$REGION" \
  --source=deploy/killswitch --entry-point=budget_killswitch \
  --trigger-topic=budget-alerts \
  --set-env-vars="GCP_PROJECT=${PROJECT},CLOUD_RUN_REGION=${REGION},CLOUD_RUN_SERVICE=${SERVICE},PAUSE_AT_FRACTION=1.0"

# 3. Billing → Budgets & alerts → create a budget (e.g. $5/mo), and under "Manage
#    notifications" connect it to the `budget-alerts` Pub/Sub topic. Also keep the default
#    50/90/100% email alerts.
```

Grant the function's runtime service account `roles/run.admin` (or a custom role with
`run.services.get`/`run.services.update`) on the project so it can pause the service.

`PAUSE_AT_FRACTION=1.0` pauses at 100% of the budget; lower it (e.g. `0.8`) to pause earlier.
