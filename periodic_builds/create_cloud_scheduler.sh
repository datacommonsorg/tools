gcloud scheduler jobs create pubsub build-all-repos --location="us-central1" --schedule="0 6 * * *" --topic=trigger-periodic-build --message-body="*" --time-zone=PST
