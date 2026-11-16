output "landing_bucket" {
  value = google_storage_bucket.landing.name
}

output "webhook_url" {
  value = google_cloud_run_v2_service.webhooks.uri
}

output "workload_identity_provider" {
  description = "Set as GitHub repository variable GCP_WIF_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Set as GitHub repository variable GCP_DEPLOY_SA."
  value       = google_service_account.deployer.email
}

output "agent_service_account" {
  value = google_service_account.agent.email
}
