terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # State in a pre-created, versioned bucket (one per environment).
  backend "gcs" {
    prefix = "hospitality-data-platform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
