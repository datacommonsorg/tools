# Bigtable Automation

## Background

This directory contains the Google Cloud Function involved in BT cache
generation. The Cloud Function first gets notified by a Borg pipeline,
via `init.txt`, when the cache files have been uploaded to GCS. As a result, it
creates a new BT table, scales-up the node-limit (for faster loads, only on base
cache), kicks off the [CsvImport Dataflow
job](https://github.com/datacommonsorg/tools/tree/master/bigtable_automation/java/dataflow)
and registers `launched.txt`.

After the dataflow job has run to completion, it notifies this Cloud Function
again, via `completed.txt`. As a result, it scales-down the node-limit (only on
base cache). In future, for branch cache, it will notify Mixer.

All of the above `.txt` files are created in a per-cache directory. So, they
allow for concurrent cache builds and tracking past state.

There are two distince GCF, one used for production imports with
entry point `ProdBTImportController` and the other used for private imports with
entry point `PrivateBTImportController`. The two functions has the same workflow
as described below, except the GCS folder structure are different. The
production entry point can be tested locally through `local/main.go`

## Validate BT Import End-to-end using (GCS | BT) Test Environment

0. First start the Cloud Function locally, as follows:

   ```bash
   ./local/deploy.sh
   ```

1. A test branch cache exists in this [folder](https://pantheon.corp.google.com/storage/browser/prophet_cache/dcbranch_2022_05_06_16_16_13).

   Just in case a test was run with that cache before, clean-up first:

   ```bash
   ./local/test.sh cleanup
   ```

2. Fake an init trigger from Google pipeline:

   ```bash
   ./local/test.sh init
   ```

   To validate this step:

   - [`prophet-test`](https://pantheon.corp.google.com/bigtable/instances/prophet-test/overview?project=google.com:datcom-store-dev)
     BT instance should have 3 nodes (instead of 1) and a new table
     `dcbranch_2022_05_06_16_16_13` under [Tables](https://pantheon.corp.google.com/bigtable/instances/prophet-test/tables?project=google.com:datcom-store-dev)

   - A dataflow job `dcbranch_2022_05_06_16_16_13` runs for ~4-5 minutes
     [here](https://pantheon.corp.google.com/dataflow/jobs?project=google.com:datcom-store-dev).

   - A directory for the cache name within
     [`gs://automation_control_test/dcbranch_2022_05_06_16_16_13`](https://pantheon.corp.google.com/storage/browser/automation_control_test/dcbranch_2022_05_06_16_16_13)
     containing a `launched.txt` file. When the dataflow job above ends, there
     should be a `completed.txt` file.

3. Fake a completion trigger from Dataflow job:

   ```bash
   ./local/test.sh completed
   ```

   Validate this step by confirming that the
   [`prophet-test`](https://pantheon.corp.google.com/bigtable/instances/prophet-test/overview?project=google.com:datcom-store-dev)
   BT instance now has 1 node.

## Deployment

After validating the change in test environment, deploy to PROD by running:

```bash
./prod/deploy.sh base
./prod/deploy.sh branch
```

When this completes, look at the
[prophet-cache-trigger](https://pantheon.corp.google.com/functions/details/us-central1/prophet-cache-trigger?organizationId=433637338589&project=datcom-store&tab=source)
on GCP console to version.

To deploy private GCF, identify the environment, pick the corresponding yaml
files in `private/*.yaml` and run

```bash
./private/deploy.sh <env>.yaml
```
