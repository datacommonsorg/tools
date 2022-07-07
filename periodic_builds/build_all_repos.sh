# Submits a cloud build job and pipes output to a file
# Moves the output file to folder `success` if return code is 0
# Otherwise, moves it to folder `failed`
#
# Parameters
# $1 is the path to the config file
# $2 is the path to the code folder
# $3 is the name of the file to pipe output to
function submit_cloud_build {
	gcloud builds submit --config $1 $2 &> $3
	if [ $? -ne 0 ]; then
		mv $3 /workspace/failed/
	else
		mv $3 /workspace/success/
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
	submit_cloud_build import/build/cloudbuild.java.yaml import import_java.out.txt
	submit_cloud_build import/build/cloudbuild.npm.yaml import import_npm.out.txt
}

function build_data {
	clone_git datacommonsorg/data
	submit_cloud_build data/cloudbuild.go.yaml data data_go.out.txt
	submit_cloud_build data/cloudbuild.py.yaml data data_py.out.txt
}

function build_mixer {
	clone_git datacommonsorg/mixer
	submit_cloud_build mixer/build/ci/cloudbuild.test.yaml mixer mixer.out.txt
}

function build_recon {
	clone_git datacommonsorg/reconciliation
	submit_cloud_build reconciliation/build/ci/cloudbuild.test.yaml reconciliation reconciliation.out.txt
}

function build_website {
	clone_git datacommonsorg/website
	submit_cloud_build website/build/ci/cloudbuild.npm.yaml website website_npm.out.txt
	submit_cloud_build website/build/ci/cloudbuild.py.yaml website website_py.out.txt
	submit_cloud_build website/build/ci/cloudbuild.webdriver.yaml website website_webdriver.out.txt
}

function build_api_python {
	clone_git datacommonsorg/api-python
	submit_cloud_build api-python/cloudbuild.yaml api-python api-python.out.txt
}

# Given a command to run, runs it with printfs right before and after it
#
# Parameters
# $1 is the name of the command to run
function build_wrapper {
	printf "Starting function $1\n"
	$1
	printf "$1 returned\n"
}

mkdir allrepos_tmp
cd allrepos_tmp

mkdir /workspace/failed
mkdir /workspace/success


# Parallelize the build functions, reference: https://stackoverflow.com/a/26240420
pids=""
build_cmds_to_run=('build_import' 'build_data' 'build_mixer' 'build_recon'
	'build_website' 'build_api_python')
for build_cmd in ${build_cmds_to_run[*]}; do
	echo "running build function: $build_cmd"
	build_wrapper $build_cmd &
	pid=$!
	echo "$build_cmd pid is $pid"
	pids="$pids $pid"
done

echo "waiting on pids: ${pids[*]}"
wait $pids
echo "all processes returned, returning."
