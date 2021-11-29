import os

import boto3
from dotenv import load_dotenv

load_dotenv('.env')

ACCESS_KEY = os.environ["s3-access-key"]
SECRET_KEY = os.environ["s3-secret-access-key"]
s3 = boto3.client("s3", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
