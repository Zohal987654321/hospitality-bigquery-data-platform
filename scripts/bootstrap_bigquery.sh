#!/usr/bin/env bash
# Creates the raw and ops datasets/tables needed to run the pipeline against a real
# BigQuery project without Terraform (quickstart). dbt creates its own datasets.
#
#   GCP_PROJECT_ID=my-project ./scripts/bootstrap_bigquery.sh
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
LOCATION="${GCP_REGION:-australia-southeast1}"

for ds in raw_pos raw_workforce raw_inventory ops; do
  if bq --project_id="$GCP_PROJECT_ID" show "$ds" >/dev/null 2>&1; then
    echo "dataset $ds exists"
  else
    bq --location="$LOCATION" mk --dataset "$GCP_PROJECT_ID:$ds"
  fi
done

mk_table() {
  local table=$1 schema=$2
  if bq --project_id="$GCP_PROJECT_ID" show "ops.$table" >/dev/null 2>&1; then
    echo "table ops.$table exists"
  else
    bq mk --table "$GCP_PROJECT_ID:ops.$table" "$schema"
  fi
}

mk_table ingestion_watermarks \
  "source:STRING,entity:STRING,watermark_value:STRING,run_id:STRING,updated_at:TIMESTAMP"
mk_table ingestion_runs \
  "run_id:STRING,source:STRING,entity:STRING,status:STRING,started_at:TIMESTAMP,finished_at:TIMESTAMP,extracted:INT64,loaded:INT64,rejected:INT64,duplicates_removed:INT64,pii_fields_removed:STRING,watermark_from:STRING,watermark_to:STRING,landing_uri:STRING,error:STRING"
mk_table reconciliation_results \
  "business_date:DATE,pos_location_id:STRING,metric:STRING,source_value:NUMERIC,warehouse_value:NUMERIC,difference:NUMERIC,within_tolerance:BOOL"

echo "BigQuery is ready in project $GCP_PROJECT_ID ($LOCATION)."
