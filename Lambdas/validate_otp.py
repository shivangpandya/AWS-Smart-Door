import json
import boto3
import time

dynamo_db_client = boto3.client('dynamodb')

def lambda_handler(event, context):
    # TODO implement
    body = json.loads(event['body'])
    otp = body['otp']
    row_identifier = body['identifier']
    print("otp: ",otp)
    print("uuid: ",row_identifier)
    if validate_details(row_identifier,otp):
        return {
            'statusCode': 200,
            'body': json.dumps('Success'),
            "headers": { "Access-Control-Allow-Origin" : "*"}
        }
    else:
        return {
            'statusCode': 403,
            'body': json.dumps('OTP doesnt match'),
            "headers": { "Access-Control-Allow-Origin" : "*"}
        }

def validate_details(row_identifier, otp):
    item = dynamo_db_client.get_item(TableName='passcodes', Key={'uuid':{'S':row_identifier}})
    print("item: ",item)
    if 'Item' in item:
        ttl = int(item['Item']['expiry_time']['N'])
        if int(time.time()) <= ttl:
            expected_otp = item['Item']['otp']['N']
            return expected_otp == otp
    return False

