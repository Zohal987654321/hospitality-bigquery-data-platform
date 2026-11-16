# Quickstart: run it on real BigQuery

Loads the synthetic data from the mock APIs into a real BigQuery project and builds
all dbt models and tests there. No Terraform, Cloud Run or Secret Manager needed.
Cost: within BigQuery's free tier (the dataset is a few MB).

## 1. Google Cloud project
1. Go to https://console.cloud.google.com, create a project (e.g. `hospitality-demo`).
2. Link billing (the free trial credit is fine). The BigQuery *sandbox* without billing
   does not allow the DELETE/MERGE statements the pipeline uses.
3. Enable the BigQuery API: APIs & Services → Library → "BigQuery API" → Enable.

## 2. Install and sign in with the Google Cloud CLI
```bash
gcloud auth login
gcloud config set project hospitality-demo
gcloud auth application-default login
gcloud auth application-default set-quota-project hospitality-demo
```

## 3. Create the raw and ops datasets
```bash
GCP_PROJECT_ID=hospitality-demo ./scripts/bootstrap_bigquery.sh
```

## 4. Load data (two terminals)
```bash
# terminal 1
make mock-api

# terminal 2
set -a && . ./.env.example && set +a
export WAREHOUSE=bigquery GCP_PROJECT_ID=hospitality-demo
python -m hospitality_elt ingest --source all
```
Check in the console: `raw_pos.transactions`, `ops.ingestion_runs`.

## 5. Build the warehouse with dbt
```bash
cd transform
export GCP_PROJECT_ID=hospitality-demo
dbt debug --profiles-dir .      # checks the connection
dbt build --profiles-dir .      # seeds, models, tests, unit test
```
The dev target writes to datasets named `dbt_<your user>_staging`, `..._marts`, `..._ai`.
Use `--target prod` to write to `staging`, `marts`, `ai`.

## 6. Look at the result
```sql
select * from `hospitality-demo.dbt_<you>_ai.daily_location_performance`
order by business_date desc, location_name
limit 20;
```

To remove everything: delete the project, or delete the datasets.
