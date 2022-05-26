import json
import pandas as pd
import time
import os
import boto3
import requests
from subprocess import call
from io import StringIO
from datetime import datetime
from aws_parameter_store import AwsParameterStore
from ssm_parameter_store import EC2ParameterStore
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import sentry_sdk
from sentry_sdk.integrations.serverless import serverless_function
sentry_sdk.init(dsn="sentry dsn")

store1 = EC2ParameterStore()
region = store1.get_parameters_by_path("/dev/data-pipeline/aws/", strip_path=True)
ld_url = store1.get_parameters_by_path("/dev/api-letsdial/", strip_path=True)
aws_region = region["region"]
user_session_url = ld_url["user-sessions-url"]
list_url = ld_url["campaignlistapi-url"]
store = AwsParameterStore(aws_region)
letsdial_clients = store.get_parameters_dict('/dev/api-letsdial/campaignlist/')
letsdial_login = store.get_parameters_dict('/dev/api-letsdial/user-login/')
letsdial_file_mapping = store.get_parameters_dict('/dev/api-letsdial/file-mapping/')
letsdial_create_campaignlist = store.get_parameters_dict('/dev/api-letsdial/create-campaignlist')
lead_selection_procs = store.get_parameters_dict('/dev/api-letsdial/lead-selection')
letsdial_campaignlist_pause = store.get_parameters_dict('/dev/api-letsdial/patchcall')
server_conn = store.get_parameters_dict('/dev/data-pipeline/server/')
s3_folders = store.get_parameters_dict('/dev/api-letsdial/folders-s3')
bucket2 = store1.get_parameters_by_path("/dev/data-pipeline/bucket/csv/", strip_path=True)
dest_bucket_name = bucket2["name"]


os.chdir('/tmp')
call('rm -rf /tmp/*', shell=True)

batch_date = (datetime.date(datetime.now()))
timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")


start_time = time.time()

s3_connection = boto3.client('s3')

def s3_exists(bucket, key):
    """return True if key  exists, else False"""
    try:
        s3_connection.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        if exc.response['Error']['Code'] != '404':
            raise
        else:
            return False


def getserver_details():
    for key, value in server_conn.items():
        server = value["server"]
        username = value["username"]
        password = value["password"]
        database = value["database"]
        yield([server, username, password, database])


for [server, username, password, database] in getserver_details():
    conn = 'DRIVER={ODBC Driver 17 for SQL Server};SERVER='+server+';DATABASE='+database+';UID='+username+';PWD='+password
    connection_url = URL.create("mssql+pyodbc", query={"odbc_connect": conn})
    engine = create_engine(connection_url)

def create_campaignlist():
    for key, value in letsdial_clients.items():
        client_name = (value["client"])
        campaignid = (value["campaignid"])
        queueid = (value["queue"])
        new_campaign = (client_name+str(batch_date))
        yield([new_campaign, campaignid, queueid])

def login():
    authenticate_url = user_session_url
    for key, value in letsdial_login.items():
        response = requests.post(authenticate_url, json=value)
        tk = (response.json()['data']['attributes']['token'])
        if response.status_code != 200:
            print('error: ' + str(response.json()))
        else:
            print('Successful login')
            return(tk)


def lead_selection_s3upload():
    s3 = boto3.resource('s3')
    for key, value in s3_folders.items():
        folder = value['s3_folder']
        s3_file_name = value['filename']+str(timestamp)
        for key, value in lead_selection_procs.items():
            client = value['client']
            proc = value['proc']
            if client in s3_file_name:
                csv_buffer = StringIO()
                df = pd.read_sql_query(proc, engine)
                df.to_csv(csv_buffer, index=None)
                s3_file_path = folder + "/" + s3_file_name + '.csv'
                if s3_exists(dest_bucket_name, s3_file_path):
                    print('File Already Exists in S3 Bucket', s3_file_path)
                else:
                    s3.Object(dest_bucket_name, s3_file_path).put(Body=csv_buffer.getvalue())


campaignlistapi_url = list_url
token = (login())
my_headers = {'Authorization': 'Bearer %s' % token}


def currentlists():
    c = requests.get(campaignlistapi_url, headers=my_headers)
    if c.status_code != 200:
        print('error: ' + str(c.json()))
    else:
        print('Successful get current campaignlist')
    for idx, item in enumerate(c.json()['data']):
        if item['relationships']['campaign']['data']['id'] == 1:  # and item['attributes']['name'] in ['Dotsure_Standard2022-04-04_124630']:
            currentlistname = (item['attributes']['name'])
            listID = (item['id'])
            campaignid = item['relationships']['campaign']['data']['id']
            queid = item['relationships']['queue']['data']['id']
            yield([currentlistname, campaignid, listID, queid])


def get_latestS3_key():
    for key, value in s3_folders.items():
        folder = value['s3_folder']
        response = s3_connection.list_objects_v2(Bucket=dest_bucket_name, Prefix=folder)
        all = response['Contents']
        latest = max(all, key=lambda x: x['LastModified'])
        s3_key = latest['Key']
        s3_file_ext = s3_key.replace(folder+'/', '')
        s3_file_name = s3_file_ext.replace('.csv', '')
        yield(s3_key, s3_file_name)


def delete_campaign():
    for currentlistname, campaignid, listID, queid in currentlists():
        if str(batch_date) not in currentlistname:
            print('deleting......', currentlistname, campaignid, listID)
            for key, value in letsdial_campaignlist_pause.items():
                value['data']['id'] = listID
                value['data']['attributes']['name'] = currentlistname
                value['data']['attributes']['diallerActive'] = False
                value['data']['relationships']['campaign']['data']['id'] = campaignid
                value['data']['relationships']['queue']['data']['id'] = queid
                pauselist = json.dumps(value)
                load_pause = json.loads(pauselist)
                delete_url = campaignlistapi_url+str(listID)
                pause = requests.patch(delete_url, json=load_pause, headers=my_headers)
                if pause.status_code != 200:
                    print('error: ' + str(pause.json()))
                else:
                    print('Successful pause of campaign')
                delete = requests.delete(delete_url, headers=my_headers)
                if delete.status_code != 204:
                    print('error: ' + str(delete.json()))
                else:
                    print('Successful deletion of campaign')


def create_campaign(s3_file_name):
    for new_campaign, campaignid, queueid in create_campaignlist():
        if new_campaign in s3_file_name:
            print('creating......', s3_file_name, campaignid)
            for key, value in letsdial_create_campaignlist.items():
                value['data']['attributes']['name'] = s3_file_name
                value['data']['attributes']['diallerActive'] = True
                value['data']['relationships']['campaign']['data']['id'] = campaignid
                value['data']['relationships']['queue']['data']['id'] = queueid
                createlist = json.dumps(value)
                new = json.loads(createlist)
                create = requests.post(campaignlistapi_url, json=new, headers=my_headers)
                if create.status_code != 201:
                    print('error: ' + str(create.json()))
                else:
                    print('Successful campaign creation')
                    listID = create.json()['data']['id']
                    yield(s3_file_name, listID)


def get_s3file(key, s3_file_name):
    file_obj = s3_connection.get_object(Bucket=dest_bucket_name, Key=key)
    body = file_obj['Body']
    csv_string = body.read().decode('utf-8')
    df = pd.read_csv(StringIO(csv_string))
    filepath = os.getcwd()
    df.to_csv(s3_file_name, index=None)
    yield(filepath, s3_file_name)

@serverless_function
def load_listfile(event, context):
    lead_selection_s3upload()
    delete_campaign()
    for s3_key, s3_file_name in get_latestS3_key():
        for new_campaign, listID in create_campaign(s3_file_name):
            print(new_campaign, listID)
            listfile_url = campaignlistapi_url+str(listID)+'/upload'
            for key, value in letsdial_file_mapping.items():
                mapping = value
                for filepath, s3_file_name in get_s3file(s3_key, s3_file_name):
                    if new_campaign in s3_file_name:
                        file_path = filepath + '/' + s3_file_name
                        fileFp = {'import_file': (s3_file_name, open(file_path, 'rb'), 'text/csv')}
                        upload = requests.post(listfile_url, headers=my_headers, files=fileFp)
                        if upload.status_code != 200:
                            print('error: ' + str(upload.json()))
                        else:
                            print('Successful file upload')
                            mapping_url = campaignlistapi_url+str(listID)+'/confirm-upload'
                            map = requests.post(mapping_url, json=mapping, headers=my_headers)
                            if map.status_code != 200:
                                print('error: ' + str(map.json()))
                            else:
                                print('Successful file mapping')
