# dc-covid19-website
Dashboard to display the top number of COVID-19 regions (State or County) in the USA by cases or deaths.

To build the project:
1. Create a config.py file in the covid19-dashboard directory.
   a. The config file should contain your DataCommons API Key as follows:``API_KEY="YOURAPIKEY"``.
2. Go to dc-covid19 and execute ``npm run build`` to build the static React files.

To deploy the project to Google Cloud App Engine:
1. Install Google Cloud Command Line Tools.
2. Set Up an App Engine Instance.
3. Login to your App Engine Instance using the Google Cloud Command Line Tools.
4. Execute ``gcloud app deploy``.
5. Execute ``gcloud app deploy cron.yaml``.

