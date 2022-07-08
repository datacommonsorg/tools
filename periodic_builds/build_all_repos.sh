# Returns the first folder in a path-like string that doesn't start with /
#
# Examples:
# foo/bar/test.txt -> foo
# foo/bar -> foo
# foo -> foo
#
# Parameters
# $1 is the pathlike string
function get_root_folder_of_path_like {
	echo $1 | cut -d'/' -f1
}

# Submits a cloud build job and pipes output to a file
# Moves the output file to folder `success` if return code is 0
# Otherwise, moves it to folder `failed`
#
# Parameters
# $1 is the path to the config file
# $2 is the path to the code folder
function submit_cloud_build {
	outfile="$1.out"
	repo_folder=$(get_root_folder_of_path_like $1)

	gcloud builds submit --config $1 $repo_folder &> $outfile

	return_code=$?
	if [ $return_code -ne 0 ]; then # if return code is not 0
		mv $3 $FAILED_FOLDER
	else
		mv $3 $SUCCESS_FOLDER
	fi
}

# Clones the GitHub Data Commons repository given by the repo string only
# git will exit without any writes if the repository already exists,
# so we can call this function multiple times with the same repo if
# necessary
#
# Example:
	# `clone_dc import` will clone `https://github.com/datacommonsorg/import`
#
# Parameters
# $1 is the name of the repo, e.g. "import" to clone datacommonsorg/import
function clone_dc {
	url="https://github.com/datacommons/$1.git"
	echo "Cloning into $1 : url is [[$url]]"
	git clone $url
}

function build_import {
	clone_dc import
	submit_cloud_build import/build/cloudbuild.java.yaml
	submit_cloud_build import/build/cloudbuild.npm.yaml
}

function build_data {
	clone_dc data
	submit_cloud_build data/cloudbuild.go.yaml
	submit_cloud_build data/cloudbuild.py.yaml
}

function build_mixer {
	clone_dc mixer
	submit_cloud_build mixer/build/ci/cloudbuild.test.yaml
}

function build_recon {
	clone_dc reconciliation
	submit_cloud_build reconciliation/build/ci/cloudbuild.test.yaml
}

function build_website {
	clone_dc website
	submit_cloud_build website/build/ci/cloudbuild.npm.yaml
	submit_cloud_build website/build/ci/cloudbuild.py.yaml
	submit_cloud_build website/build/ci/cloudbuild.webdriver.yaml
}

function build_api_python {
	clone_dc api-python
	submit_cloud_build api-python/cloudbuild.yaml
}

cd $TMP_FOLDER

mkdir $SUCCESS_FOLDER
mkdir $FAILED_FOLDER


# Parallelize the build functions, reference: https://stackoverflow.com/a/26240420
pids=""
build_cmds_to_run=('build_import' 'build_data' 'build_mixer' 'build_recon'
	'build_website' 'build_api_python')
for build_cmd in ${build_cmds_to_run[*]}; do
	echo "running build function: $build_cmd"
	$build_cmd &
	pid=$!
	pids="$pids $pid"
done

echo "all jobs launched, waiting for them to complete to return"
wait $pids
echo "all processes returned, returning."
