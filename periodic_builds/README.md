This folder contains a pair of a cloudbuild yaml and a bash script that clones
and builds all Data Commons repositories.

To launch this build job, run the following at this folder
(`tools/periodic_builds`).
You'll need to have `gcloud` installed.
```
gcloud builds submit --config cloudbuild.allrepos.yaml .
```
