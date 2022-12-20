#!/bin/bash

set -x

create_fresh_bt_table_for_testing () {
  gcloud config set project google.com:datcom-store-dev
  cbt -instance prophet-test deletetable $TABLE 2>/dev/null
  cbt -instance prophet-test createtable $TABLE || { echo "createtable failed!"; exit 1; }
  cbt -instance prophet-test createfamily $TABLE csv || { echo "createfamily failed!"; exit 1; }
}


if [[ "$1" == "deploy" ]]; then

  mvn compile exec:java -Dexec.mainClass=org.datacommons.dataflow.CsvImport -Dexec.args="--runner=DataflowRunner --project=google.com:datcom-store-dev --stagingLocation=gs://datcom-dataflow-templates/test_staging --templateLocation=gs://datcom-dataflow-templates/templates/csv_to_bt_test --region=us-central1 --usePublicIps=false"

elif [[ "$1" == "deploy-flex" ]]; then

  # Build the Uber-jar.
  mvn clean package

  # From pom.xml
  TAG="0.0.2-SNAPSHOT"

  # Submit a build job to create a Docker image for the flex template.
  gcloud dataflow flex-template build \
    "gs://datcom-dataflow-templates/templates/flex/csv_to_bt_test.json" \
     --image-gcr-path "gcr.io/datcom-ci/dataflow-templates/csv2bt:$TAG" \
     --sdk-language "JAVA" \
     --flex-template-base-image JAVA11 \
     --metadata-file "csv2bt-template-metadata.json" \
     --jar "target/dataflow-$TAG.jar" \
     --project=datcom-ci \
     --env FLEX_TEMPLATE_JAVA_MAIN_CLASS="org.datacommons.dataflow.CsvImport"

elif [[ "$1" == "run-cache" ]]; then

  if [[ $# != 2 ]]; then
    echo "Usage: $0 run-cache <CACHE_NAME>" >&2
    exit 1
  fi
  TABLE=$2
  JOB_SUFFIX="${TABLE//_/-}" # Job names cannot have underscores.

  create_fresh_bt_table_for_testing

  gcloud dataflow jobs run test-csv2bt-${JOB_SUFFIX} \
    --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt_test \
    --region us-central1 \
    --parameters inputFile=gs://datcom-store/${TABLE}/cache.csv*,completionFile=gs://automation_control_test/finished-${TABLE}.txt,bigtableInstanceId=prophet-test,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev

elif [[ "$1" == "run-cache-flex" ]]; then

  if [[ $# != 2 ]]; then
    echo "Usage: $0 run-cache-flex <CACHE_NAME>" >&2
    exit 1
  fi
  TABLE=$2

  create_fresh_bt_table_for_testing

  JOB_SUFFIX="${TABLE//_/-}" # Job names cannot have underscores.

  gcloud dataflow flex-template run test-csv2bt-flex-${JOB_SUFFIX} \
    --template-file-gcs-location \
      "gs://datcom-dataflow-templates/templates/flex/csv_to_bt_test.json" \
    --parameters inputFile="gs://datcom-store/${TABLE}/cache.csv*" \
    --parameters completionFile="gs://automation_control_test/finished-${TABLE}.txt" \
    --parameters bigtableInstanceId="prophet-test" \
    --parameters bigtableTableId=${TABLE} \
    --parameters bigtableProjectId=google.com:datcom-store-dev \
    --parameters tempLocation=gs://datcom-store-dev-resources/tmp \
    --region "us-central1" \
    --disable-public-ips

elif [[ "$1" == "run-csv" ]]; then

  if [[ $# != 3 ]]; then
    echo "Usage: $0 run-csv <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
    exit 1
  fi
  TABLE=$2
  CSV_FILE=$3
  JOB_SUFFIX="${TABLE//_/-}" # Job names cannot have underscores.

  create_fresh_bt_table_for_testing

  gcloud dataflow jobs run test-csv2bt-${JOB_SUFFIX}-csv \
    --gcs-location gs://datcom-dataflow-templates/templates/csv_to_bt_test \
    --parameters inputFile=${CSV_FILE},completionFile=gs://automation_control_test/finished-${TABLE}.txt,bigtableInstanceId=prophet-test,bigtableTableId=${TABLE},bigtableProjectId=google.com:datcom-store-dev

elif [[ "$1" == "run-csv-flex" ]]; then

  if [[ $# != 3 ]]; then
    echo "Usage: $0 run-csv-flex <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
    exit 1
  fi
  TABLE=$2
  CSV_FILE=$3
  JOB_SUFFIX="${TABLE//_/-}" # Job names cannot have underscores.

  create_fresh_bt_table_for_testing

  gcloud dataflow flex-template run test-csv2bt-flex-${JOB_SUFFIX}-csv \
    --template-file-gcs-location \
      "gs://datcom-dataflow-templates/templates/flex/csv_to_bt_test.json" \
    --parameters inputFile="${CSV_FILE}" \
    --parameters completionFile="gs://automation_control_test/finished-${TABLE}.txt" \
    --parameters bigtableInstanceId="prophet-test" \
    --parameters bigtableTableId=${TABLE} \
    --parameters bigtableProjectId=google.com:datcom-store-dev \
    --parameters tempLocation=gs://datcom-store-dev-resources/tmp \
    --region "us-central1" \
    --disable-public-ips

else
  echo "Classic Templates:" >&2
  echo "Usage: $0 deploy" >&2
  echo "Usage: $0 run-cache <CACHE_NAME>" >&2
  echo "Usage: $0 run-csv <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
  echo "Flex Templates:" >&2
  echo "Usage: $0 deploy-flex" >&2
  echo "Usage: $0 run-cache-flex <CACHE_NAME>" >&2
  echo "Usage: $0 run-csv-flex <BT_TABLE_NAME> <GCS_CSV_FILE>" >&2
  exit 1
fi

