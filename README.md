# dialer-data-loader

The dialer-data-loader loads data selected from the database and archived to the s3 bucket to the dialer.

# usage

# 1. apiDataload.py

## 1.1 s3_exists

This function checks if a key or file exists in the s3 bucket.
Parameters required for s3_exists are:

- bucket = bucket_name
- key = s3_file_path

## 1.2 getserver_details

This function returns server details from AWS Parameter store. Parameters required for getserver_details are:

- server = server
- username = username
- password = password
- database = database

## 1.3 create_campaignlist

This function returns the dialer client details from AWS Parameter store and creates a new campaign name based on the current date timestamp. Parameters required for getserver_details are:

- client_name = client
- campaignid = campaignid
- queueid = dialer queue id
- new_campaign = client_name + batch_date

## 1. 4 login

This function returns lets dial's log in credentials, creates a log in request and returns a token from the request. Parameters required for login are:

- username and passowrd = json payload
- authenticate_url = login api

## 1.5 lead_selection_s3upload

This function selects data to be loaded for the day and uploads the data as a csv file in the s3 bucket. Parameters required for lead_selection_s3upload are:

- proc = stored procedure
- engine = database connection
- dest_bucket_name = s3 bucket name
- s3_file_path = s3 filename

## 1.6 currentlists

This function returns the currentlistname, campaignid and listid of the campaignlists that have been loaded to the dialer. Parameters required for currentlists are:

- campaignlistapi_url = campaign list api
- my_headers = token

## 1.7 get_latestS3_key

This function retrieves the latest file dropped in the s3 bucket and returns the s3 key and filename. Parameters required for get_latestS3_key are:

- dest_bucket_name = s3 bucket name
- folder = s3 prefix

## 1.8 create_campaign

This function deletes any previous batches that are in the camapignlist queue. It then creates a new current campaignlist and returns the s3 file name and listID. Parameters required for create_campaign are:

- currentlistname = current campaign list name
- campaignid = dialer campaign id
- listID = campaign list id
- new_campaign = new campaign list name
- queueid = dialer queue id
- delete_url = campaign list api + campaign list id
- campaignlistapi_url = campaign list api
- my_headers = token
- new = json payload for creating a new campaign

## 1.9 get_s3file

This function calls the get_latestS3_key function and retrieves the lastest file uploaded to the s3 bucket and converts the file object to a dataframe. The dataframe is then convereted to a csv file and written to memory. It returns the filename and the path of the file. Parameters required for get_s3file are:

- dest_bucket_name = s3 bucket name
- key = s3 key

## 1.10 load_listfile

This function calls the create_campaign and get_s3file functions and imports the created file and uploads it to the dialer.Parameters required for load_listfile are:

- listfile_url = campaign list api + campaign list id +'/upload'
- mapping = json payload for mapping an uploaded file
- s3_file_name = file to be uploaded
- fileFp = file object
- mapping_url = campaign list api + campaign list id +'/confirm-upload'
- my_headers = token
