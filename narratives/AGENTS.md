# Custom Data Commons - Workspace Rules

## 1. Ingestion Pipeline configuration (`config.json`)
When creating or modifying `config.json` files for ingestion, **always use the dictionary format** with explicit `columnMappings` instead of the array format. 
Using the array format (e.g., `{"inputFiles": [{"csv": "data.csv"}]}`) can cause the ingestion preprocessing container to silently hang and deadlock.
Example of the correct format:
```json
{
  "inputFiles": {
    "observations.csv": {
      "columnMappings": {
        "Date": "ObservationDate",
        ...
      }
    },
    "schema.mcf": {}
  }
}
```

## 2. Executing the Preprocessing Cloud Run Job
When manually triggering the preprocessing job (`dcapp-dc-ingestion-preprocessing-job`) on Cloud Run, **never batch multiple datasets together**. 
Passing multiple datasets via a single comma-separated list (like `--args=^:^--imports=dataset1,dataset2`) will cause the container to silently deadlock and hang forever right after the "Merging config" step is completed. 
**ALWAYS execute datasets sequentially, one by one**.

Example of correct execution (one dataset):
```bash
gcloud run jobs execute dcapp-dc-ingestion-preprocessing-job --args=--imports=dataset_name --project custom-data-commons --region us-central1 --wait
```

If multiple datasets need to be processed, use a bash loop or python script to iterate through them sequentially.
