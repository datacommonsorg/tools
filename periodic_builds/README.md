# Periodic Builds

This folder contains code for a Google Cloud Build job that builds the
configurations listed in `builds.txt`.

It is meant to be used for periodic builds of all Data Commons repositories so
that errors can be caught early. The scheduling of this job is handled by Google
Cloud Scheduler and therefore is outside the scope of this script.

## Overview of the Job

[`cloudbuild.allrepos.yaml`](cloudbuild.allrepos.yaml) is
the entry point of the Cloud Build job. It includes two steps;
1. `build_all_repos.sh`: In an image where `gcloud` is installed, read
   `builds.txt`, clones repositories, and submits Cloud Build jobs with the
   configuration specificied in `builds.txt` (see below for syntax). Build logs
   are streamed to a file `<cloudbuild_yaml_name>.out` and moved to
   `$SUCCESS_FOLDER` or `$FAILED_FOLDER` as defined in
   `cloudbuild.allrepos.yaml` based on whether the launched build was successful
   or not.
2. `notify_results.sh`: In a golang image, failed output files are read from
   `$FAILED_FOLDER` and emails are sent using `main.go`.

## Specifying Builds in `builds.txt`

`builds.txt` is a text file, where each line is the path to a cloudbuild
configuration file (`cloudbuild.yaml`) that will be run as part of this job.

Each path should be in the form:

```
<dc_repo_name>/path/to/cloudbuild.yaml
```

where `<dc_repo_name>` is the name of the repository under the `datacommonsorg`
GitHub account where the build file can be found.

To add a new build to the periodic builds suite, add a line `builds.txt`
according to the syntax above. For example, if we wanted to add a build called
`cloudbuild.goldens.yaml` in the path `build/ci` in a `datacommonsorg`
repository named `myshinyrepo`, you would add the following line to `builds.txt`:

```
myshinyrepo/build/ci/cloudbuild.goldens.yaml
```

## Launching this Build Manually

This build can be launched manually if you have `gcloud` installed. Note that
you should set your project to `datcom-ci` (or another cloud project with the
necessary requisities installed, such as the secrets used my `main.go`)

Then, make sure you in this folder;

```
cd tools/periodic_builds
```

And launch the build job using;
```
gcloud builds submit --config cloudbuild.allrepos.yaml .
```

## Design Choices

[Google Cloud Documentation](https://cloud.google.com/build/docs/running-builds/start-build-command-line-api#api)
outlines the process of using the CLI or API to programmatically launch Cloud
Build jobs.

Using the API requires that the source code is already within the Google Cloud
environment (either Cloud Storage or Cloud Source Repository).

The CLI command `gcloud builds submit` automatically compresses the source code
in a `tar` archive, uploads it to Google Cloud Storage, and then uses the API
to launch a Cloud Build Job.

Since the CLI abstracts away the details of compressing the source code and
interacting with Google Cloud Storage, this folder is programmed in `bash`
instead of using a programming language with the API and one of the client
libraries.

## Debugging Resources

All resources live in the `datcom-ci` project.

Google Cloud Scheduler job `build-all-repos` triggers every morning at 6am PST.
- [Cloud Scheduler Dashboard](https://pantheon.corp.google.com/cloudscheduler?referrer=search&mods=-monitoring_api_staging&project=datcom-ci)
- [`build-all-repos` schedule logs](https://pantheon.corp.google.com/logs/query;query=resource.type%3D%22cloud_scheduler_job%22%20AND%20resource.labels.job_id%3D%22build-all-repos%22%20AND%20resource.labels.location%3D%22us-central1%22;timeRange=P7D;cursorTimestamp=2022-08-08T13:00:00.220726227Z?mods=-monitoring_api_staging&project=datcom-ci)

Google Cloud PubSub Topic `trigger-periodic-build` receives the message from
Cloud Scheduler.
- [Cloud PubSub Dashboard](https://pantheon.corp.google.com/cloudpubsub/topic/list?mods=-monitoring_api_staging&project=datcom-ci)
- [Cloud PubSub `trigger-periodic-build` page](https://pantheon.corp.google.com/cloudpubsub/topic/detail/trigger-periodic-build?mods=-monitoring_api_staging&project=datcom-ci)

Google Cloud Build trigger `periodic-build-all-repos` subscribes to
`trigger-periodic-build` topic and launches a job when messages are sent to it.
- [Cloud Build Dashboard](https://pantheon.corp.google.com/cloud-build/triggers?mods=-monitoring_api_staging&project=datcom-ci)
- [`trigger-periodic-build` build history](https://pantheon.corp.google.com/cloud-build/builds;region=global?query=trigger_id%3D%22e966047b-5226-4a84-aa5e-23e9387c8265%22&mods=-monitoring_api_staging&project=datcom-ci) will show periodic builds that ran.
- To see jobs launched by the periodic build job, you'll need to look at [Cloud Build History](https://pantheon.corp.google.com/cloud-build/builds?mods=-monitoring_api_staging&project=datcom-ci&pageState=(%22builds%22:(%22f%22:%22%255B%255D%22))). Jobs launched by periodic builds are unique in that they 1) have a source of "Google Cloud Storage" 2) they are launched close to 6am, and 3) they don't have a ref/commit/trigger name associated with them.

Google Cloud Storage (GCS) is where the builds read the code from. All code is in the
bucket `datcom-ci_cloudbuild`
- [`datcom-ci_cloudbuild` bucket browser](https://pantheon.corp.google.com/storage/browser/datcom-ci_cloudbuild;tab=objects?forceOnBucketsSortingFiltering=false&mods=-monitoring_api_staging&project=datcom-ci&prefix=&forceOnObjectsSortingFiltering=false)
- To get the exact source an individual build ran on, go to the build logs of that individiual build and click the "source" link. You can download the tar archive from GCS and look around/run tests to understand failures.
  - If there are files/folders missing from this archive that are otherwise on
	GitHub, check if those paths are in `.gitignore`. The `gcloud` CLI used to
	launch individual jobs has a default ignore behavior where paths in
	`.gitignore` are not uploaded to GCS. This might cause a discrepancy between
	build results for periodic builds and builds that use `git clone`.

## Manual Steps

To get this to work automatically, Cloud Scheduler can be used to trigger a
Cloud Build trigger at a regular schedule; for example, we want to do every day
at 6am PST.

Code to create this Cloud Scheduler job is in `create_cloud_scheduler.sh`. Note
that you must create a Cloud Build Trigger that will run on the PubSub topic
`trigger-periodic-build` for this to work.
