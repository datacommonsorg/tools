#!/bin/bash

set -x

if [[ "$1" == "deploy" ]]; then

  mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=google.com:datcom-store-dev --stagingLocation=gs://datcom-dataflow-templates/test_staging --templateLocation=gs://datcom-dataflow-templates/templates/csv_to_bt_test --region=us-central1"

elif [[ "$1" == "run-cache" ]]; then

  if [[ $# != 2 ]]; then
    echo "Usage: $0 run-cache <CACHE_NAME>" >&2
    exit 1
  fi
  TABLE=$2

  gcloud config set project google.com:datcom-store-dev
  cbt -instance prophet-test deletetable $TABLE 2>/dev/null
  cbt -instance prophet-test createtable $TABLE || { echo "createtable failed!"; exit 1; }
  cbt -instance prophet-test createfamily $TABLE csv || { echo "createfamily failed!"; exit 1; }

  gcloud dataflow jobs run test-csv2bt-${TABLE} \
    --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt_test \
    --parameters inputFile=gs://datcom-store/${TABLE}/cache.csv*,completionFile=gs://automation_control_test/finished-${TABLE}.txt,bigtableInstanceId=prophet-test,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev

elif [[ "$1" == "run-csv" ]]; then

  if [[ $# != 3 ]]; then
    echo "Usage: $0 run-csv <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
    exit 1
  fi
  TABLE=$2
  CSV_FILE=$3

  gcloud config set project google.com:datcom-store-dev
  cbt -instance prophet-test deletetable $TABLE 2>/dev/null
  cbt -instance prophet-test createtable $TABLE || { echo "createtable failed!"; exit 1; }
  cbt -instance prophet-test createfamily $TABLE csv || { echo "createfamily failed!"; exit 1; }

  gcloud dataflow jobs run test-csv2bt-${TABLE}-csv \
    --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt_test \
    --parameters inputFile=${CSV_FILE},completionFile=gs://automation_control_test/finished-${TABLE}.txt,bigtableInstanceId=prophet-test,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev

else
  echo "Usage: $0 deploy" >&2
  echo "Usage: $0 run-cache <CACHE_NAME>" >&2
  echo "Usage: $0 run-csv <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
  exit 1
fi
