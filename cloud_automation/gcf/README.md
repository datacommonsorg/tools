This directory contains Google Cloud Function involved in BT cache generation.

# `bt_trigger.go`

This Cloud Function, with entry point `BTImportController`, first gets notified
by the Google3 pipeline, via `init.txt`, when the cache files have been uploaded
to GCS. As a result, it creates a new BT table, scales-up the node-limit (for
faster loads, only on base cache), kicks off the [CsvImport Dataflow
job](https://github.com/datacommonsorg/tools/tree/master/cloud_automation/java/dataflow)
and registers `launched.txt`.

After the dataflow job has run to completion, it notifies this Cloud Function
again, via `completed.txt`. As a result, it scales-down the node-limit (only on
base cache). In future, for branch cache, it will notify Mixer.

All of the above `.txt` files are created in a per-cache directory. So, they
allow for concurrent cache builds and tracking past state.

The Cloud Function supports two environments: Prod and Test (refer to
`environments` global in the source file). The default is Prod, while Test env
is only used for local testing of the function via `cmd/main.go`.

## Build

To build the cloud function locally:

```
cd cmd
go build main.go
```

## Validate BT Import End-to-end using (GCS | BT) Test Environment

0.  First start the Cloud Function locally, as follows:

    ```
    cd cmd
    go run main.go
    ```

1. Pick a recent branch cache build to use for the test---any `branch_` prefix
   directory from [`prophet-cache`
   bucket](https://pantheon.corp.google.com/storage/browser/prophet_cache;tab=objects)
   will do.

2. Fake an init trigger from Google pipeline:

    ```
    ./test.sh branch_2021_01_08_13_25_48 init
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

2. Fake a completion trigger from Dataflow job:

    ```
    ./test.sh branch_2021_01_08_13_25_48 completed
    ```

    Validate this step by confirming that the
    [`prophet-test`](https://pantheon.corp.google.com/bigtable/instances/prophet-test/overview?project=google.com:datcom-store-dev)
    BT instance now has 1 node.


# `airflow_trigger.py`

This is part of an older deprecated flow.

TODO(pradh): Remove this when we have fully switched over to improved flow.
