# Bigtable Automation

BT automation works as follows:

1. The Prophet Generator Borg job notifies a
   [Cloud Function](https://pantheon.corp.google.com/functions/details/us-central1/prophet-cache-trigger?project=datcom-store&tab=general)
   (GCF)
   which creates a new BT table, scales up BT resources (for base cache builds
   only) and kicks off the
   [CSV-to-BT Dataflow job](https://pantheon.corp.google.com/dataflow/jobs?organizationId=433637338589&project=datcom-store)
   stored in
   [datcom-dataflow-templates](https://pantheon.corp.google.com/storage/browser/_details/datcom-templates/templates/flex/csv_to_bt_0.0.3.json).

2. When the Dataflow job completes, it notifies the same cloud function to
   scale down BT resources (for base cache builds only).

3. The notifications between Borg-to-GCF and Dataflow-to-GCF happen using
   per-version state files located in GCS:

   - Base cache:
     [/bigstore/datcom-control/base/{BT_Table}/...](https://pantheon.corp.google.com/storage/browser/datcom-control/base)
   - Branch cache:
     [/bigstore/datcom-control/branch/{BT_Table}/...](https://pantheon.corp.google.com/storage/browser/datcom-control/branch)
   - Private cache:
     [/bigstore/<private-bucket>/.../<import_group>/control/{BT_Table}/](https://pantheon.corp.google.com/storage/browser/datcom-control/branch)

   Borg job sets `init`, then GCF on launching the Dataflow job sets `launched`
   and Dataflow job on completion sets `completed`.

4. The Borg job polls for a fixed timeout on the `launched` and `completed`
   state files to track progress and completion.

## [Cloud Function](gcf/README.md)

## [Dataflow Job](java/dataflow/README.md)

## Custom DC Import

Custom DC import automation follows similar flow as above but the GCS, GCF,
Bigtable and Dataflow are in custom GCP projects. These have to be configured
before hand and in the yaml files under [private config](gcf/private/).

## Deployment to Custom DC instances using Terraform

BigTable instance and the associated Cloud Function can be deployed into a custom DC GCP project using Terraform. Below are the steps for doing so. Note that it assumes a resource bucket is already created.

1. From terraform diretory, replace placeholder values in [`variables.tfvars`](bigtable_automation/terraform/variables.tfvars). Those are the required variables. For a complete list of what is configurable, please see [`variables.tf`](bigtable_automation/terraform/variables.tf).

2. Run the following command to deploy BT and GCF.

```sh
terraform init && terraform apply --var-file="variables.tfvars" -auto-approve
```
