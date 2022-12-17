#!/bin/bash
# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
# <cloudbuild_path_name>.out.<repo>
# Moves the output to $SUCCESS_FOLDER if the build job completes
# successfully, or to $FAILED_FOLDER otherwise.
#
# Parameters
# $1 is the path to the config file from builds.txt
function submit_cloud_build {
	# extract information from $1 to use later
	repo=$(get_root_folder_of_path_like $1)
	cloudbuild_path=$(echo $1 | cut -d"/" -f2-) # get path without repo name
	cloudbuild_link="https://github.com/datacommonsorg/$repo/blob/master/$cloudbuild_path"

	# appending $1 to the beginning of the filenames makes sure that the
	# filenames are unique so that the concurrent processes don't write over
	# each other.
	buildlog_file="$1.command_out.txt" # output of the command gets stored here
	header_file="$1.tmp_header.txt" # quick-access information get added to the top
	tmp_file="$1.tmp.txt" # used temporarily when merging header and command
	# outfile gets moved to $SUCCESS_FOLDER or $FAILED_FOLDER and gets emailed
	# if $FAILED_FOLDER
	outfile="$1.out.$repo" # header_file + buildlog_file gets written to outfile

	# "> $buildlog_file" redirects stdout to write to $buildlog_file
	# "2>&1" redirects "stderr" to where "stdout" is going
	# The result is that both stdout and stderr are written to $buildlog_file
	gcloud builds submit --config $1 $repo > $buildlog_file 2>&1
	return_code=$? # store the return code of the gcloud command

	# create a header file that will include the first few lines of the email
	# to make it easier to parse quickly.
	# first line; email subject (used by notify_results.sh)
	echo "[Periodic Builds] Error building datacommonsorg/$1" > $header_file
	# second line; link to cloud build log page
	cat $buildlog_file | sed -n "s/Logs are available at/Cloud Build Logs:/p" >> $header_file
	# third line; link to the cloudbuild yaml file that this was ran with
	echo "Link to the failing cloudbuild.yaml file: $cloudbuild_link" >> $header_file
	# fourth line; divider between links and build output
	# we use printf instead of echo here because it handles \n properly
	printf "\n\n----FULL BUILD OUTPUT----\n\n" >> $header_file

	# create the final output file by appending $header_file to the top of
	# $output_file
	cat $header_file $buildlog_file > $tmp_file && mv $tmp_file $outfile

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
