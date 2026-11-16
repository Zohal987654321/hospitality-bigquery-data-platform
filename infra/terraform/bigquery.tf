locals {
  datasets = {
    raw_pos       = "Raw POS API data (append-only, JSON payload). Ingestion only."
    raw_workforce = "Raw workforce data, PII removed/pseudonymised at ingestion. Ingestion only."
    raw_inventory = "Raw inventory SFTP exports. Ingestion only."
    ops           = "Pipeline state: watermarks, run log, reconciliation results."
    reference     = "dbt seeds: venue crosswalk, budgets."
    staging       = "dbt staging views: typed, deduplicated source data."
    intermediate  = "dbt intermediate models."
    marts         = "Analytics-ready facts and dimensions for reporting."
    ai            = "Curated, documented views for AI agents and internal apps."
    dq_failures   = "Rows that failed dbt data tests (for investigation)."
  }
}

resource "google_bigquery_dataset" "ds" {
  for_each    = local.datasets
  dataset_id  = each.key
  location    = var.bq_location
  description = each.value
  labels      = merge(local.labels, { layer = each.key })

  # Test-failure tables are for investigation only: expire them after 14 days.
  default_table_expiration_ms = each.key == "dq_failures" ? 1209600000 : null

  delete_contents_on_destroy = false

  depends_on = [google_project_service.apis]
}

# ---------- ops tables ----------
resource "google_bigquery_table" "watermarks" {
  dataset_id          = google_bigquery_dataset.ds["ops"].dataset_id
  table_id            = "ingestion_watermarks"
  deletion_protection = true
  schema = jsonencode([
    { name = "source", type = "STRING", mode = "REQUIRED" },
    { name = "entity", type = "STRING", mode = "REQUIRED" },
    { name = "watermark_value", type = "STRING", mode = "REQUIRED" },
    { name = "run_id", type = "STRING", mode = "NULLABLE" },
    { name = "updated_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "runs" {
  dataset_id          = google_bigquery_dataset.ds["ops"].dataset_id
  table_id            = "ingestion_runs"
  deletion_protection = true

  time_partitioning {
    type = "DAY"
  }

  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "source", type = "STRING", mode = "REQUIRED" },
    { name = "entity", type = "STRING", mode = "REQUIRED" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "finished_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "extracted", type = "INT64", mode = "NULLABLE" },
    { name = "loaded", type = "INT64", mode = "NULLABLE" },
    { name = "rejected", type = "INT64", mode = "NULLABLE" },
    { name = "duplicates_removed", type = "INT64", mode = "NULLABLE" },
    { name = "pii_fields_removed", type = "STRING", mode = "NULLABLE" },
    { name = "watermark_from", type = "STRING", mode = "NULLABLE" },
    { name = "watermark_to", type = "STRING", mode = "NULLABLE" },
    { name = "landing_uri", type = "STRING", mode = "NULLABLE" },
    { name = "error", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "reconciliation" {
  dataset_id          = google_bigquery_dataset.ds["ops"].dataset_id
  table_id            = "reconciliation_results"
  deletion_protection = true
  schema = jsonencode([
    { name = "business_date", type = "DATE", mode = "REQUIRED" },
    { name = "pos_location_id", type = "STRING", mode = "REQUIRED" },
    { name = "metric", type = "STRING", mode = "REQUIRED" },
    { name = "source_value", type = "NUMERIC", mode = "NULLABLE" },
    { name = "warehouse_value", type = "NUMERIC", mode = "NULLABLE" },
    { name = "difference", type = "NUMERIC", mode = "NULLABLE" },
    { name = "within_tolerance", type = "BOOL", mode = "NULLABLE" },
  ])
}

# Webhook events landed by the receiver, queryable without a load step.
resource "google_bigquery_table" "webhook_events" {
  dataset_id          = google_bigquery_dataset.ds["raw_pos"].dataset_id
  table_id            = "webhook_events_external"
  deletion_protection = false

  external_data_configuration {
    autodetect    = true
    source_format = "NEWLINE_DELIMITED_JSON"
    compression   = "GZIP"
    source_uris   = ["gs://${google_storage_bucket.landing.name}/webhooks/pos/*"]

    hive_partitioning_options {
      mode              = "AUTO"
      source_uri_prefix = "gs://${google_storage_bucket.landing.name}/webhooks/pos/"
    }
  }
}

# ---------- authorised dataset ----------
# Views in `ai` may read `marts` on behalf of whoever queries them, so agents get
# access to the curated views without any direct grant on marts.
resource "google_bigquery_dataset_access" "ai_reads_marts" {
  dataset_id = google_bigquery_dataset.ds["marts"].dataset_id
  dataset {
    dataset {
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.ds["ai"].dataset_id
    }
    target_types = ["VIEWS"]
  }
}
