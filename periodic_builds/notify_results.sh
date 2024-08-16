# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


for f in $FAILED_FOLDER/*
do
	printf "Sending email for failed file; $(basename $f)\n"
	subject=$(head $f -n 1)
	go run main.go \
	  --subject="$subject" \
	  --receiver="datacommons-alerts@google.com" \
	  --body_file="$f" \
	  --mime_type="text/plain"
done

printf "count success: $(ls -l $SUCCESS_FOLDER | wc -l)\n\n"
printf "success: \n $(ls -l $SUCCESS_FOLDER)\n\n"

printf "\n\n\n"

printf "count failed: $(ls -l $FAILED_FOLDER | wc -l)\n\n"
printf "failed: \n $(ls -l $FAILED_FOLDER)\n\n"
