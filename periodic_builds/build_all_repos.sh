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
	echo $repo_folder
	return 0
	gcloud builds submit --config $1 $repo_folder &> $outfile
	if [ $? -ne 0 ]; then
		mv $3 $FAILED_FOLDER
	else
		mv $3 $SUCCESS_FOLDER
	fi
}

# Clones the GitHub repository given by the username/repo string only
#
# Parameters
# $1 is the "<user>/<repo>" string, e.g. "datacommonsorg/import"
function clone_git {
	url="https://github.com/$1.git"
	echo "Cloning into $1 : url is [[$url]]"
	git clone $url
	echo "Clone complete for $1 : url was [[$url]]"
}

function build_import {
	clone_git datacommonsorg/import
	submit_cloud_build import/build/cloudbuild.java.yaml
	submit_cloud_build import/build/cloudbuild.npm.yaml
}

function build_data {
	clone_git datacommonsorg/data
	submit_cloud_build data/cloudbuild.go.yaml
	submit_cloud_build data/cloudbuild.py.yaml
}

function build_mixer {
	clone_git datacommonsorg/mixer
	submit_cloud_build mixer/build/ci/cloudbuild.test.yaml
}

function build_recon {
	clone_git datacommonsorg/reconciliation
	submit_cloud_build reconciliation/build/ci/cloudbuild.test.yaml
}

function build_website {
	clone_git datacommonsorg/website
	submit_cloud_build website/build/ci/cloudbuild.npm.yaml
	submit_cloud_build website/build/ci/cloudbuild.py.yaml
	submit_cloud_build website/build/ci/cloudbuild.webdriver.yaml
}

function build_api_python {
	clone_git datacommonsorg/api-python
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
	echo "$build_cmd pid is $pid"
	pids="$pids $pid"
done

echo "waiting on pids: ${pids[*]}"
wait $pids
echo "all processes returned, returning."
