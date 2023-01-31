# Custom DC BT automation

## Backgroud

Custom DC BT automation also triggers KG builders owned by the DC team by writing to a blob in the resource bucket.

The blob written to the following path will trigger a cache build.
```sh
gs://<resource-bucket>/../<import name>/process/<import id>/trigger.txt
```

## How to test

From custom_dc directory, run `./deploy_local.sh` to start custom DC gcf locally.

### Testing csv trigger

From gcf directory, run `./custom_dc/test.sh publish`.
