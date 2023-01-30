# Custom DC BT automation

## Backgroud

Custom DC BT automation also triggers KG builders owned by the DC team on new CSV files in the resource bucket.

## How to test

From custom_dc directory, run `go run main.go` to start custom DC gcf locally.

### Testing csv trigger

From gcf directory, run `./custom_dc/test.sh publish`.
