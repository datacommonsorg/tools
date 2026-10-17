# Terraform state backend.
# State for each instance lives at
# gs://<project_id>-tfstate/custom-datacommons/<instance>/.
# deploy.sh creates the bucket and turns on versioning before the first apply,
# so this backend can be initialized.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    # Set via -backend-config on terraform init, e.g.
    #   terraform init -backend-config="bucket=<project_id>-tfstate" \
    #                  -backend-config="prefix=custom-datacommons/<instance>"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
