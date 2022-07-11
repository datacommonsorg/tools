BUILDS_FILE="$PWD/builds.txt"

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

# Submits a cloud build job and pipes output to a file that is in the format
# <repo>.<cloudbuild_path_name>.out
# Moves the output to $SUCCESS_FOLDER if the build job completes
# successfully, or to $FAILED_FOLDER otherwise.
#
# Parameters
# $1 is the path to the config file from builds.txt
function submit_cloud_build {
	repo=$(get_root_folder_of_path_like $1)
	outfile="$repo.$1.out"

	# Start the output file with a live GitHub link to the cloudbuild file that
	# this job is running.
	cloudbuild_path=$(echo $1 | cut -d"/" -f2-) # get path without repo name
	cloudbuild_link="https://github.com/datacommonsorg/$repo/blob/master/$cloudbuild_path"
	echo "Link to this cloudbuild:" > $outfile
	echo "$cloudbuild_link" >> $outfile

	# ">> $outfile" redirects stdout to append to $outfile
	# "2>&1" redirects "stderr" to where "stdout" is going
	# The result is that both stdout and stderr are appended to $outfile
	gcloud builds submit --config $1 $repo >> $outfile 2>&1

	return_code=$?
	if [ $return_code -ne 0 ]; then # if return code is not 0
		mv $outfile $FAILED_FOLDER
	else
		mv $outfile $SUCCESS_FOLDER
	fi
}

# Clones the GitHub Data Commons repository given by the repo string only
# git will exit without any writes if the repository already exists,
# so we can call this function multiple times with the same repo if
# necessary
#
# Example:
	# `clone_dc import` will clone `https://github.com/datacommonsorg/import.git`
#
# Parameters
# $1 is the name of the repo, e.g. "import" to clone datacommonsorg/import
function clone_dc {
	url="https://github.com/datacommonsorg/$1.git"
	echo "Cloning into $1 : url is [[$url]]"
	git clone $url
}

function main {
	# Move to the $TMP_FOLDER defined from the environment and
	# create SUCCESS and FAILED folders
	cd $TMP_FOLDER
	mkdir $SUCCESS_FOLDER
	mkdir $FAILED_FOLDER

	# Synchronously clone git repositories
	while read -r cloudbuild_path; do
		clone_dc $(get_root_folder_of_path_like $cloudbuild_path)
	done < "$BUILDS_FILE"

	# Launch the build jobs in parallel, accumulating process IDs
	# in $pids. reference: https://stackoverflow.com/a/26240420
	pids=""
	while read -r cloudbuild_path; do
		echo "running cloudbuild: $cloudbuild_path"
		submit_cloud_build $cloudbuild_path &
		pid=$! # $! is the process ID of the last command ran
		pids="$pids $!"
	done < "$BUILDS_FILE"

	# Wait for all jobs to return before returning
	echo "all jobs launched, waiting for them to complete to return"
	wait $pids
	echo "all processes returned, returning."
}

main
