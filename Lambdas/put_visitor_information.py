import json
import uuid
import time
import boto3
import base64
import random

s3 = boto3.resource('s3')
S3_BUCKET_NAME = "smart-door-visitor-faces-cc"
rekog_client = boto3.client('rekognition')
dynamo_db_client = boto3.client('dynamodb')
sns_client = boto3.client('sns')
SENDER = "Gaurav Agrawal <ga1380@nyu.edu>"

def lambda_handler(event, context):
    # TODO implement
    body = json.loads(event["body"])
    visitor_phone_number = body["phone_number"]
    visitor_name = body["name"]
    visitor_name = visitor_name.replace(" ","_")
    visitor_image_base64_string = body["base64_encoded_image"].split(",")[1]
    unique_file_name = "{}_{}.jpeg".format(visitor_name,str(uuid.uuid1()))
    save_image_in_s3(unique_file_name, visitor_image_base64_string)
    face_id = index_new_visitor_face(unique_file_name)
    insert_in_db2(visitor_name,visitor_phone_number,unique_file_name, face_id)
    row_identifier = str(uuid.uuid1())
    otp = get_random_otp()
    insert_in_passcode_table(row_identifier,face_id,otp)
    send_sms_to_visitor(visitor_phone_number,row_identifier,otp)
    return {
        'statusCode': 200,
        'body': json.dumps('Success'),
        "headers": { "Access-Control-Allow-Origin" : "*"}
    }

def save_image_in_s3(unique_file_name, visitor_image_base64_string):
    object = s3.Object(S3_BUCKET_NAME,unique_file_name)
    object.put(Body=base64.b64decode(visitor_image_base64_string),ContentType="image/jpeg",ContentEncoding="base64")

def index_new_visitor_face(unique_file_name):
    indexed_face = rekog_client.index_faces(CollectionId="smart-door",
                                Image={'S3Object':{'Bucket':S3_BUCKET_NAME,'Name':unique_file_name}},
                                ExternalImageId=unique_file_name,
                                MaxFaces=1,
                                QualityFilter="AUTO",
                                DetectionAttributes=['ALL'])
    face_id = indexed_face['FaceRecords'][0]['Face']['FaceId']
    return face_id

def insert_in_db2(visitor_name, visitor_phone_number, unique_file_name, face_id):
    print("insert_in_visitors")
    expiry_time = int(time.time()) + 5*60
    d = [{
                                                        'bucket':S3_BUCKET_NAME,
                                                        'objectKey':unique_file_name,
                                                        'createdTimestamp' : str(time.time())
                                                    }]
    dynamo_db_client.put_item(TableName='visitors', Item={'faceId':{'S':face_id}
                                                    ,'name':{'S': visitor_name}
                                                    , 'phone_number' : {'S' : visitor_phone_number}
                                                    , 'photos' : {'S' : str(d)}
    })

def get_random_otp():
    print("get_random_otp")
    otp = 0
    for i in range(1,5):
        otp += random.randint(0,9)
        otp*=10
    return otp

def insert_in_passcode_table(row_identifier, known_person_face_id, otp):
    print("insert_in_passcode_table")
    expiry_time = int(time.time()) + 5*60
    dynamo_db_client.put_item(TableName='passcodes', Item={'uuid':{'S':row_identifier}
                                                    ,'expiry_time':{'N': str(expiry_time)}
                                                    , 'faceId' : {'S' : str(known_person_face_id)}
                                                    , 'otp' : {'N' : str(otp)}
    })

def send_sms_to_visitor(visitor_phone_number, row_identifier, otp):
    #print("send_sms_to_visitor")
    #message = "Otp : {}\nClick Here: {}".format(otp, row_identifier)
    #sns_client.publish(PhoneNumber=visitor_phone_number,Message=message)
    print("send_sms_to_visitor")
    message = "Otp : {}\nClick Here: http://smart-door-website.s3-website-us-east-1.amazonaws.com/otp.html?uuid={}".format(otp, row_identifier)
    print("message: ",message)
    check = sns_client.publish(PhoneNumber=visitor_phone_number,Message=message)
    print("sns response",check)
    SUBJECT = "Your OTP to open the door"
    BODY_TEXT = ("Amazon SES Test (Python)\r\n"
             "This email was sent with Amazon SES using the "
             "AWS SDK for Python (Boto)."
            )
    BODY_HTML = """<html>
                    <head></head>
                    <body>
                      <h1>"""+"Your OTP is {}".format(otp)+"""</h1>
                      <p>
                        <a href="""+"http://smart-door-website.s3-website-us-east-1.amazonaws.com/otp.html?uuid={}".format(row_identifier)+""">Click Here</a> using the
                      </p>
                    </body>
                    </html>
                """
    CHARSET = "UTF-8"
    # client = boto3.client('ses')
    # response = client.send_email(
    #     Destination={
    #         'ToAddresses': [
    #             visitor_phone_number,
    #         ],
    #     },
    #     Message={
    #         'Body': {
    #             'Html': {
    #                 'Charset': CHARSET,
    #                 'Data': BODY_HTML,
    #             },
    #             'Text': {
    #                 'Charset': CHARSET,
    #                 'Data': message,
    #             },
    #         },
    #         'Subject': {
    #             'Charset': CHARSET,
    #             'Data': SUBJECT,
    #         },
    #     },
    #     Source=SENDER)
    # print("ses response",response)