# Security and governance

## Sensitive data is removed before it is stored

`pii.py` runs inside the ingestion job, **before** anything is written to Cloud Storage
or BigQuery. Raw tables therefore never hold direct identifiers.

| Data | Treatment |
|---|---|
| Employee names, email, phone, address, date of birth | Dropped |
| Tax file number, bank BSB/account, super details | Dropped |
| Pay rate, salary, award classification | Dropped (shift-level labour cost is kept — it is needed for labour %) |
| Employee ID, manager ID, POS staff ID | Pseudonymised: keyed HMAC-SHA256 (key in Secret Manager). Stable, so joins work; not reversible without the key. |
| Customer details and card data on transactions | Dropped |

Two layers make this robust:
1. A **per-entity policy** lists the fields to drop or pseudonymise.
2. A **deny-list scan** removes any key at any nesting depth that looks like contact,
   identity or banking data. If a vendor adds `emergency_contact_phone` next month, it
   never reaches the warehouse.

Each run records which fields were removed in `ops.ingestion_runs.pii_fields_removed`,
which gives an audit trail without storing the values.

If the business later needs identified employee data (e.g. payroll reconciliation), it
belongs in a separate restricted dataset with its own service account — not in the
analytics layers.

## Identity and access (least privilege)

| Principal | Access |
|---|---|
| `sa-hosp-ingest` | Writes raw/ops, runs dbt; reads only its own secrets; writes the landing bucket. |
| `sa-hosp-webhooks` | Can only *create* objects in the landing bucket; reads one secret. |
| `sa-hosp-agent` | Reads the `ai` dataset only. `ai` views reach `marts` through an **authorised dataset**, so agents have no direct grant on marts, staging or raw. |
| `sa-hosp-scheduler` | Can only invoke the two Cloud Run jobs. |
| `sa-hosp-deployer` | GitHub Actions via Workload Identity Federation, restricted to `main` of this repository. No JSON keys exist. |
| Analysts group | Reads `marts` and `ai`. |

All grants are dataset- or resource-level, not project-wide (except `bigquery.jobUser`,
which only allows running jobs).

## Secrets

- Stored in Secret Manager, replicated in-region only, read at start-up, never logged.
- Terraform creates secret containers but never values, so nothing secret is in state.
- SFTP uses key authentication with a pinned host key (no trust-on-first-use).
- Webhooks are authenticated with HMAC signatures and reject requests older than 5 minutes.

## Data residency and retention

- All datasets, the bucket and compute are in `australia-southeast1` (Sydney).
- Landing files move to Nearline after 30 days and Archive after a year; rejected
  records are deleted after 90 days; test-failure tables expire after 14 days.

## SOC 2-relevant controls in this design

Change management (PR review + CI on every change, deploys only from `main`), access
control (per-workload service accounts, no keys), logging (structured logs, run log,
BigQuery audit logs), monitoring and alerting, and data integrity checks
(contracts, tests, reconciliation).
