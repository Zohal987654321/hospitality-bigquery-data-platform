# Least privilege: one service account per workload, dataset-level grants only.
#
#   sa-hosp-ingest     writes raw_* and ops, writes landing bucket, reads its secrets,
#                      runs dbt (reads raw/reference, writes staging..ai)
#   sa-hosp-webhooks   writes webhook events to the landing bucket only
#   sa-hosp-agent      reads the `ai` dataset only (MCP server / AI apps)
#   sa-hosp-scheduler  may only trigger the Cloud Run jobs
#   sa-hosp-deployer   used by GitHub Actions via Workload Identity Federation

resource "google_service_account" "ingest" {
  account_id   = "sa-hosp-ingest"
  display_name = "Hospitality ingestion + transform jobs"
}

resource "google_service_account" "webhooks" {
  account_id   = "sa-hosp-webhooks"
  display_name = "Hospitality webhook receiver"
}

resource "google_service_account" "agent" {
  account_id   = "sa-hosp-agent"
  display_name = "AI agents (read-only, ai dataset)"
}

resource "google_service_account" "scheduler" {
  account_id   = "sa-hosp-scheduler"
  display_name = "Cloud Scheduler invoker"
}

resource "google_service_account" "deployer" {
  account_id   = "sa-hosp-deployer"
  display_name = "GitHub Actions deployer"
}

# ---- BigQuery: job execution is project-level, data access is dataset-level ----
resource "google_project_iam_member" "job_user" {
  for_each = {
    ingest = google_service_account.ingest.email
    agent  = google_service_account.agent.email
  }
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${each.value}"
}

resource "google_bigquery_dataset_iam_member" "ingest_editor" {
  for_each   = toset(["raw_pos", "raw_workforce", "raw_inventory", "ops", "reference", "staging", "intermediate", "marts", "ai", "dq_failures"])
  dataset_id = google_bigquery_dataset.ds[each.value].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_bigquery_dataset_iam_member" "agent_viewer" {
  dataset_id = google_bigquery_dataset.ds["ai"].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_bigquery_dataset_iam_member" "analysts" {
  for_each   = var.analyst_group == "" ? toset([]) : toset(["marts", "ai"])
  dataset_id = google_bigquery_dataset.ds[each.value].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = var.analyst_group
}

# ---- Storage ----
resource "google_storage_bucket_iam_member" "ingest_landing" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_storage_bucket_iam_member" "webhooks_landing" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.webhooks.email}"
}

# ---- GitHub Actions: keyless deploys via Workload Identity Federation ----
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  # Only the main branch of this repository can deploy.
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/run.developer",
    "roles/artifactregistry.writer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Deployer must be able to deploy jobs that run as the workload service accounts.
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    ingest   = google_service_account.ingest.name
    webhooks = google_service_account.webhooks.name
    agent    = google_service_account.agent.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
