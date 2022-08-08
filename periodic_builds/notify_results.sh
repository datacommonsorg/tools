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
