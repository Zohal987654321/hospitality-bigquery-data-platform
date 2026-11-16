locals {
  common_env = {
    HOSPITALITY_ENV            = var.environment
    GCP_PROJECT_ID             = var.project_id
    GCP_REGION                 = var.region
    LANDING_BUCKET             = google_storage_bucket.landing.name
    OPS_DATASET                = "ops"
    POS_BASE_URL               = var.pos_base_url
    WORKFORCE_BASE_URL         = var.workforce_base_url
    SFTP_HOST                  = var.sftp_host
    SFTP_USERNAME              = var.sftp_username
    INCREMENTAL_LOOKBACK_HOURS = "48"
    MAX_REJECT_RATIO           = "0.05"
    DBT_TARGET                 = "prod"
  }

  jobs = {
    # Full daily load: all sources -> dbt build (models + tests) -> reconciliation -> notify
    "hosp-daily" = {
      args     = ["daily"]
      timeout  = "3600s"
      retries  = 2
      memory   = "2Gi"
      schedule = var.daily_schedule
    }
    # Intraday sales refresh for same-day dashboards (raw only; staging views are live)
    "hosp-intraday-pos" = {
      args     = ["ingest", "--source", "pos", "--entity", "transactions"]
      timeout  = "900s"
      retries  = 1
      memory   = "1Gi"
      schedule = var.intraday_sales_schedule
    }
  }
}

resource "google_cloud_run_v2_job" "jobs" {
  for_each            = local.jobs
  name                = each.key
  location            = var.region
  labels              = local.labels
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = google_service_account.ingest.email
      timeout         = each.value.timeout
      max_retries     = each.value.retries

      containers {
        image = var.image
        args  = each.value.args

        resources {
          limits = {
            cpu    = "1"
            memory = each.value.memory
          }
        }

        dynamic "env" {
          for_each = local.common_env
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  lifecycle {
    # CI updates the image on every deploy.
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "webhooks" {
  name                = "hosp-webhooks"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.webhooks.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.image
      args  = ["serve-webhooks"]

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

# Vendors call the webhook without Google credentials; requests are authenticated
# by HMAC signature inside the app instead.
resource "google_cloud_run_v2_service_iam_member" "webhooks_public" {
  name     = google_cloud_run_v2_service.webhooks.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
