# CSVImport Template

The CSVImport dataflow template creates dataflow jobs to ingest CSV data from
GCS to Cloud Bigtable.

The template is stored at  gs://datcom-dataflow-templates/templates

To deploy changes to the template run the following commands.

## Improved Flow

```
  mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=google.com:datcom-store-dev --stagingLocation=gs://datcom-dataflow-templates/improved_staging --templateLocation=gs://datcom-dataflow-templates/templates/csv_to_bt_improved --region=us-central1"

```

To perform a trial run of the Improved flow, run:

```
TABLE=branch_2021_01_08_13_25_48
cbt createtable $TABLE
cbt createfamily $TABLE csv

gcloud dataflow jobs run job-${TABLE}-1 \
  --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt_improved \
  --parameters inputFile=gs://prophet_cache/${TABLE}/cache.csv*,completionFile=gs://automation_control/completed-${TABLE}.txt,bigtableInstanceId=prophet-cache,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev
```


## Legacy Flow

IMPORTANT: Set the `USE_IMPROVED_FLOW` bool in CsvImport.java to false before
running the command below.

```
  mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=google.com:datcom-store-dev --stagingLocation=gs://datcom-dataflow-templates/staging --templateLocation=gs://datcom-dataflow-templates/templates/csv_to_bt --region=us-central1"

```

To perform a trial run of the legacy flow, run:

```
TABLE=borgcron_2021_01_11_01_01_38
cbt createtable $TABLE
cbt createfamily $TABLE csv

gcloud dataflow jobs run job-${TABLE}-1 \
  --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt \
  --parameters inputFile=gs://prophet_cache/${TABLE}/cache.csv*,bigtableInstanceId=prophet-cache,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev
```


