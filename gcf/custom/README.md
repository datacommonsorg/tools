# Custom DC BT automation

## Backgroud

Custom DC BT automation also triggers KG builders owned by the DC team by writing to a blob in the resource bucket.

The blob written to the following path will trigger a cache build.

```sh
gs://<resource-bucket>/../<import name>/process/<import id>/trigger.txt
```

## How to test

Run `./local/deploy.sh` to start custom DC gcf locally.

### Testing csv trigger

Run `./local/test.sh publish`.
