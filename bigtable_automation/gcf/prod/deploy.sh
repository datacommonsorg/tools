#!/bin/bash

# Prepare directory
mkdir -p /tmp/deploy_bt_gcf
cp bt_trigger.go go.mod /tmp/deploy_bt_gcf
cd /tmp/deploy_bt_gcf

gcloud config set project datcom-store
gcloud functions deploy prophet-cache-trigger \
  --region 'us-central1' \
  --entry-point BTImportController \
  --runtime go116 \
  --trigger-bucket datcom-control
