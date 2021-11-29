import os

import boto3
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_KEY = os.environ["s3_access_key"]
SECRET_KEY = os.environ["s3_secret_access_key"]
s3 = boto3.client("s3", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
