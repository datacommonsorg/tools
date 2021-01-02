# DC Tools Default App

This is the `default` app for the App Engine Project.
When the user visits `somesite.com/`, they will be served by the `default` app.
If the user visits `somesite.com/dashboard/`, they will be served by the `dashboard` app.

**NOTE:** The path `/dashboard` and  `/dashboard/` paths are different!
Hence why we want to redirect `/dashboard` path to the correct path, otherwise you will see a blank screen.

## Main.py

A Flask server that redirects the following paths:

1. `/` to `/dashboard?dashboardId=covid19` (temporary)
2. `/dashboard` to `/dashboard?dashboardId=covid19`.
3. `/covid19` to `/dashboard?dashboardId=covid19`.
4. `socialWellness` to `/dashboard?dashboardId=socialWelness`


## App.yaml

This is the configuration of the `default` app.
It simply tells App Engine to run app using Python.


## To Deploy The Default application
The best way to deploy the application is by using the [`deploy_gcloud.sh`](`../covid19-dashboard/deploy_gcloud.sh`) script found in `covid19-dashboard`.
If you only wish to deploy the `default` application and not use the covid-19 script, you can deploy using the following commands:

```bash
# Change variable if deploying to different project.
export GOOGLE_CLOUD_PROJECT="datcom-tools-staging"

# Set the project on gcloud.
gcloud config set project $GOOGLE_CLOUD_PROJECT

# Deploy to App Engine.
gcloud app deploy app.yaml

```
