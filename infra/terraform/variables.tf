variable "project_id" {
  type        = string
  description = "GCP project that hosts the data platform."
}

variable "region" {
  type        = string
  default     = "australia-southeast1"
  description = "Region for Cloud Run, Scheduler, Artifact Registry and the landing bucket."
}

variable "bq_location" {
  type        = string
  default     = "australia-southeast1"
  description = "BigQuery dataset location (keep data in Australia)."
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "image" {
  type        = string
  description = "Container image for the ingestion jobs, e.g. REGION-docker.pkg.dev/PROJECT/hospitality/elt:SHA. Updated by CI on each deploy."
}

variable "github_repository" {
  type        = string
  description = "owner/repo allowed to deploy via Workload Identity Federation."
}

variable "alert_email" {
  type        = string
  description = "Address that receives pipeline failure alerts."
}

variable "pos_base_url" {
  type = string
}

variable "workforce_base_url" {
  type = string
}

variable "sftp_host" {
  type    = string
  default = ""
}

variable "sftp_username" {
  type    = string
  default = ""
}

variable "analyst_group" {
  type        = string
  default     = ""
  description = "Google group (group:analysts@example.com) with read access to marts."
}

variable "daily_schedule" {
  type        = string
  default     = "30 4 * * *"
  description = "Cron (Australia/Sydney) for the full daily load: after the 4am trading-day cutoff."
}

variable "intraday_sales_schedule" {
  type        = string
  default     = "0 10-23/2 * * *"
  description = "Cron (Australia/Sydney) for intraday POS refreshes during trading hours."
}
