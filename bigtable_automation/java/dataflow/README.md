# CSVImport Template

The CSVImport dataflow template creates dataflow jobs to ingest CSV data from
GCS to Cloud Bigtable.

The template is stored at [gs://datcom-templates/templates](https://pantheon.corp.google.com/storage/browser/datcom-templates/templates).

## Build

### Compile

```sh
# In bigtable_automation/java/dataflow
mvn compile
```

### Uber-jar

Uber-jars package the compiled classes and all dependency jars into a single jar under target.

```sh
# In bigtable_automation/java/dataflow
mvn clean package
```

## Validation

### Classic Templates

1.  Deploy change to the test template for validation.

    ```sh
    ./test.sh deploy
    ```

2.  Pick a recent branch cache build to use for the test---any `branch_` prefix
    directory from [`datcom-store`
    bucket](https://pantheon.corp.google.com/storage/browser/datcom-store;tab=objects)
    will do.

3.  Run the Dataflow job in the test BT environment against the test template.

    ```sh
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

```sh

./test.sh run-csv <BT_TABLE_NAME> <GCS_CSV_FILE>

```

For example:

```sh

./test.sh run-csv mixer_test_bt gs://datcom-store-test/mixer_test_cache.csv

```

Where, `mixer_test_bt` is the BT table that will be created from
`gs://datcom-store-test/mixer_test_cache.csv`.

### Flex Templates

[Flex Templates](https://cloud.google.com/dataflow/docs/guides/templates/using-flex-templates) are a new generation of Dataflow templates that packages dependencies in the form of a Docker image instead of Jars.

The same pipeline code can generate both Classic and Flex templates. Flex templates can be validated the same way using the steps above by adding "-flex" to the subcommands like the following.

```sh
./test.sh deploy-flex
./test.sh run-cache-flex branch_2021_01_08_13_25_48
./test.sh run-csv-flex mixer_test_bt gs://datcom-store-test/mixer_test_cache.csv
```

## Production Deployment

After validating the change in test environment, deploy it to PROD template by
running the following command.

### Deploying Classic Template

```sh

mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=datcom-store --stagingLocation=gs://datcom-templates/staging --templateLocation=gs://datcom-templates/templates/csv_to_bt --region=us-central1 --usePublicIps=false"

```

NOTE: Running this may throw an exception, but as long as it says `BUILD
SUCCESS` the template has been updated.

### Deploying Flex Template

NOTE: If the version in pom.xml changes, please update TAG field below as well.

```sh

TAG="0.0.2-SNAPSHOT"

mvn clean package && gcloud dataflow flex-template build \
    "gs://datcom-dataflow-templates/templates/flex/csv_to_bt.json" \
     --image-gcr-path "gcr.io/datcom-ci/dataflow-templates/csv2bt:$TAG" \
     --sdk-language "JAVA" \
     --flex-template-base-image JAVA11 \
     --metadata-file "csv2bt-template-metadata.json" \
     --jar "target/dataflow-$TAG.jar" \
     --project=datcom-store \
     --env FLEX_TEMPLATE_JAVA_MAIN_CLASS="org.datacommons.dataflow.CsvImport"

```

The `image-gcr-path` field is the image to be built, does not have to exist.
