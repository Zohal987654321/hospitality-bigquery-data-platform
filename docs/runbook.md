# Runbook

## Where to look first

```sql
-- Latest run per source entity
select * except(rn) from (
  select *, row_number() over (partition by source, entity order by started_at desc) rn
  from ops.ingestion_runs
  where started_at > timestamp_sub(current_timestamp(), interval 3 day)
) where rn = 1
order by source, entity;

-- Reconciliation mismatches
select * from ops.reconciliation_results
where not within_tolerance
order by business_date desc;
```

Logs: Cloud Logging → `resource.type="cloud_run_job"` and `jsonPayload.run_id="<run_id>"`.
Failed dbt tests write the offending rows to the `dq_failures` dataset (kept 14 days).

## How failures are handled automatically

| Failure | What happens |
|---|---|
| API returns 429 / 5xx / network error | Retried with exponential backoff and jitter (5 attempts). |
| OAuth token expires or is revoked | Refreshed automatically; one retry on 401. |
| Some records break the data contract | Written to `gs://…/rejected/` with error details; the rest load. |
| More than 5% of a batch breaks the contract | Batch is **not** loaded, watermark not advanced, run marked failed. |
| One source is down | Other sources still load; the run is reported as failed. |
| Job crashes half-way | Cloud Run retries the execution (2 retries). Loads delete-then-insert by `run_id`, so a retry never duplicates rows. Watermarks only move after a successful load. |
| dbt test fails | Run reported as failed; failing rows stored in `dq_failures`. |
| Warehouse totals differ from the vendor's report | Row in `ops.reconciliation_results`, ERROR log, alert. |
| Job didn't run at all | "No successful loads in 6h" alert policy fires. |

## Common tasks

### Re-run after an outage
Nothing special: the next scheduled run starts from the last good watermark minus 48 hours.
To run now:
```bash
gcloud run jobs execute hosp-daily --region australia-southeast1 --wait
```

### Backfill a period
```bash
gcloud run jobs execute hosp-daily --region australia-southeast1 --wait \
  --args="ingest,--source,pos,--entity,transactions,--since,2026-07-01T00:00:00+00:00"
gcloud run jobs execute hosp-daily --region australia-southeast1 --wait --args="transform"
```
Re-loading overlapping data is safe: staging keeps the latest version of each record.

### Rebuild an incremental model from scratch
```bash
dbt build --select fct_sales_lines+ --full-refresh --target prod
```

### Replay a batch from the landing zone
Every load's file is recorded in `ops.ingestion_runs.landing_uri`. Load it again with
`bq load --source_format=NEWLINE_DELIMITED_JSON` into a scratch table, or re-run the
ingestion with `--since` covering the period.

### Rotate a credential
```bash
printf '%s' "$NEW" | gcloud secrets versions add pos-client-secret --data-file=-
gcloud secrets versions disable <old-version> --secret pos-client-secret
```
Jobs read `latest` at start-up, so the next run uses the new value.
**Do not rotate `pii-hmac-key`** without a migration plan — it changes every employee key.

### A new venue opens
Add a row to `transform/seeds/location_crosswalk.csv` (and the budget seed), open a PR.
Until then `assert_every_pos_location_is_mapped` fails, so a missing venue can't go unnoticed.

## Adding a new source system

1. Add a contract in `schemas.py` (only the fields downstream models need).
2. Add a `Source` subclass in `sources/` with an `EntitySpec` per entity, including a
   `PiiPolicy`. Implement `extract(entity, since)`.
3. Register it in `cli.build_source` and `SOURCES`; add its secrets in `secrets.tf` and
   its `raw_<source>` dataset in `bigquery.tf`.
4. Add the source and staging models in `transform/models/staging/<source>/`, with tests.
5. Add pytest coverage (see `tests/test_pipeline.py` for the pattern).

Purchasing, financial planning and other exports follow the inventory (file) or POS (API) pattern.
