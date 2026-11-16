# Alerts do not depend on the app's chat webhook: they come from Cloud Logging.

resource "google_monitoring_notification_channel" "email" {
  display_name = "Data platform on-call"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

# Counts structured log lines the pipeline emits on failure.
resource "google_logging_metric" "pipeline_failures" {
  name   = "hospitality_pipeline_failures"
  filter = <<-EOT
    resource.type="cloud_run_job"
    severity>=ERROR
    jsonPayload.event=("ingestion_failed" OR "dbt_failed" OR "reconciliation_mismatch" OR "run_log_failed")
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key        = "event"
      value_type = "STRING"
    }
  }

  label_extractors = {
    event = "EXTRACT(jsonPayload.event)"
  }
}

resource "google_monitoring_alert_policy" "pipeline_failures" {
  display_name = "Hospitality pipeline failure"
  combiner     = "OR"

  conditions {
    display_name = "Pipeline logged a failure"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.pipeline_failures.name}\" AND resource.type=\"cloud_run_job\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  documentation {
    mime_type = "text/markdown"
    content   = "A data load, dbt build or reconciliation failed. See docs/runbook.md and query `ops.ingestion_runs` for the failing run."
  }
}

# Catches jobs that never ran at all (scheduler or image problem). The intraday POS
# job loads every 2h during trading, so 6h of silence always means something is wrong.
resource "google_logging_metric" "daily_success" {
  name   = "hospitality_daily_load_complete"
  filter = "resource.type=\"cloud_run_job\" AND jsonPayload.event=\"load_complete\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "no_loads" {
  display_name = "Hospitality: no successful loads in 6h"
  combiner     = "OR"

  conditions {
    display_name = "No load_complete events"
    condition_absent {
      filter   = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.daily_success.name}\" AND resource.type=\"cloud_run_job\""
      duration = "21600s"
      aggregations {
        alignment_period   = "3600s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]
}
