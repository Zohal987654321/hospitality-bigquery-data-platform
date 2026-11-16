# Secret *containers* only. Values are added out-of-band (never in Terraform state):
#   printf '%s' "$VALUE" | gcloud secrets versions add pos-client-secret --data-file=-
locals {
  ingest_secrets = [
    "pos-client-id",
    "pos-client-secret",
    "workforce-api-key",
    "sftp-private-key",
    "sftp-host-key",
    "pii-hmac-key",
    "alert-webhook-url",
  ]
  webhook_secrets = ["webhook-secret-pos"]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(concat(local.ingest_secrets, local.webhook_secrets))
  secret_id = each.value
  labels    = local.labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Each service account can read only the secrets it needs.
resource "google_secret_manager_secret_iam_member" "ingest" {
  for_each  = toset(local.ingest_secrets)
  secret_id = google_secret_manager_secret.secrets[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_secret_manager_secret_iam_member" "webhooks" {
  for_each  = toset(local.webhook_secrets)
  secret_id = google_secret_manager_secret.secrets[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.webhooks.email}"
}
