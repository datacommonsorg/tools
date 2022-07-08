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
according to the syntax above.

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
