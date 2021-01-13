This directory contains Google Cloud Function involved in BT cache generation.

# `bt_trigger.go`

This Cloud Function, with entry point `BTImportController`, first gets notified
by the Google3 pipeline when the cache files have been uploaded into GCS, via
`init.txt`. As a result, it creates a new BT table, scales-up the node-limit
(for faster loads, only on base cache), kicks off the [CsvImport Dataflow
job](https://github.com/datacommonsorg/tools/tree/master/cloud_automation/java/dataflow)
and registers `launched.txt`.

After the dataflow job has run to completion, it notifies this Cloud Function
again, via `completed.txt`. As a result, it scales-down the node-limit (only on
base cache). In future, for branch cache, it will notify Mixer.

There function supports two environments: Prod and Test (refer to `environments`
global in the source file). Test env is only used for local testing of the
function via `cmd/main.go`.

## Validation

To validate that the cloud function builds, first start up the function locally,
as follows:

```
cd cmd
# This will build and start the serving function...
go run main.go
```

0. Tweak the `test.sh` script to use a recent branch cache (instead of
   `branch_2021_01_08_13_25_48`).

1. Fake a trigger from Google pipeline, run:

    ```
    ./test.sh init
    ```

    To validate this step:

    *  [`prophet-test`](https://pantheon.corp.google.com/bigtable/instances/prophet-test/overview?project=google.com:datcom-store-dev)
       BT instance should have 3 nodes (instead of 1) and a new table
       corresponding to the branch cache name you set in `test.sh`.

    *  A dataflow job, prefixed by `test-csv2bt-`, that runs for ~4-5 minutes
       [here](https://pantheon.corp.google.com/dataflow/jobs?project=google.com:datcom-store-dev).

    *  A directory for the cache name within
       [`gs://automation_control_test/base/`](https://pantheon.corp.google.com/storage/browser/automation_control_test/base?project=google.com:datcom-store-dev)
       containing a `launched.txt` file. When the dataflow job above ends, there
       should be a `completed.txt` file.

3. Fake a dataflow completion trigger.

    ```
    ./test.sh completed
    ```

    Validate this step by confirming that the
    [`prophet-test`](https://pantheon.corp.google.com/bigtable/instances/prophet-test/overview?project=google.com:datcom-store-dev)
    BT instance now has 1 node.

# `airflow_trigger.py`

This is part of an older deprecated flow.

TODO(pradh): Remove this when we have fully switched over to improved flow.
