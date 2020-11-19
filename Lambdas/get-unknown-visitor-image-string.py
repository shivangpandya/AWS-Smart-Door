import json
import boto3

dynamo_db_client = boto3.client('dynamodb')


def lambda_handler(event, context):
    print(event)
    # TODO implement
    uuid = event['queryStringParameters']['uuid']
    base64_encoded_image_string = get_unknown_visitor_image(uuid)
    if base64_encoded_image_string is not "":
        return {
            'statusCode': 200,
            'body': base64_encoded_image_string,
            "headers": {"Access-Control-Allow-Origin": "*"}
        }
    else:
        return {
            'statusCode': 200,
            'body': "Invalid UUID",
            "headers": {"Access-Control-Allow-Origin": "*"}
        }


def get_unknown_visitor_image(uuid):
    print("get_unknown_visitor_image")
    item = dynamo_db_client.get_item(TableName='unauthorized_visitors', Key={'uuid': {'S': uuid}})
    print(json.dumps(item, indent=2), "****")
    if "Item" in item:
        return item['Item']['base64_encoded_image']['S']
    return ""
