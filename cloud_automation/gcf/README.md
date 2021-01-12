This directory contains Google Cloud Functions involved in BT cache generation.

To validate that the cloud function builds, run:

```
cd cmd
# This will build and start the serving function...
go run main.go
```

To test the cloud function locally:

NOTE: tweak the script to use a recent branch cache.

```
# To create cache and fire off dataflow (follow the output from main.go above).
./test.sh init

# To signal dataflow job completion, and scale down resources.
./test.sh completed
```