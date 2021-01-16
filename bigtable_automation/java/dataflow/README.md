# CSVImport Template

The CSVImport dataflow template creates dataflow jobs to ingest CSV data from
GCS to Cloud Bigtable.

The template is stored at [gs://datcom-dataflow-templates/templates](https://pantheon.corp.google.com/storage/browser/datcom-dataflow-templates/templates).

## Build

```
# In bigtable_automation/java/dataflow
mvn compile
```

## Validation

1.  Deploy change to the test template for validation.

    ```
    ./test.sh deploy
    ```

2.  Pick a recent branch cache build to use for the test---any `branch_` prefix
    directory from [`prophet-cache`
    bucket](https://pantheon.corp.google.com/storage/browser/prophet_cache;tab=objects)
    will do.

3.  Run the Dataflow job in the test BT environment against the test template.

    ```
    ./test.sh run-cache branch_2021_01_08_13_25_48
    ```

4.  A dataflow job, prefixed by `test-csv2bt-` should have started
    [here](https://pantheon.corp.google.com/dataflow/jobs?project=google.com:datcom-store-dev).
    It will run for ~5 minutes. Confirm it succeeeds.

5.  A file prefixed by `finished-` should have been updated in
    [`gs://automation_control_test/`](https://pantheon.corp.google.com/storage/browser/automation_control_test?project=google.com:datcom-store-dev).

### One-off test with CSV file

If you have a one-off CSV file that you want to load into the test environment,
run the following command:

```
./test.sh run-csv mixer_test_bt gs://datcom-store-test/mixer_test_cache.csv
```

Where, `mixer_test_bt` is the BT table that will be created from
`gs://datcom-store-test/mixer_test_cache.csv`.

## Production Deployment

After validating the change in test environment, deploy it to PROD template by
running the following command.

```
mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=google.com:datcom-store-dev --stagingLocation=gs://datcom-dataflow-templates/improved_staging --templateLocation=gs://datcom-dataflow-templates/templates/csv_to_bt_improved --region=us-central1"
```

NOTE: Running this may throw an exception, but as long as it says `BUILD
SUCCESS` the template has been updated.
