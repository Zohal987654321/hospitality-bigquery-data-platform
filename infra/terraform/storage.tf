# Landing zone: an immutable copy of every extracted batch (replay + audit).
resource "google_storage_bucket" "landing" {
  name                        = "${var.project_id}-hospitality-landing"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }

  # Rejected records may contain unexpected data: keep them for 90 days only.
  lifecycle_rule {
    condition {
      age            = 90
      matches_prefix = ["rejected/"]
    }
    action {
      type = "Delete"
    }
  }
}
