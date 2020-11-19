import json
import base64
import random
import uuid
import boto3
import time
import cv2
from boto3.dynamodb.conditions import Key

dynamo_db_client = boto3.client('dynamodb')
sns_client = boto3.client('sns')
kvs_client = boto3.client('kinesisvideo')
dynamodb_resource = boto3.resource('dynamodb')
rekognition_client = boto3.client('rekognition')
SENDER = "Gaurav Agrawal <ga1380@nyu.edu>"


def lambda_handler(event, context):
    # TODO implement
    print("temporary print")
    # print(json.dumps(event, indent=2))
    process_records(event['Records'])

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }


def process_records(records):
    print("process_records")
    for record in records:
        video_information = get_video_information(record['kinesis'])
        face_search_response = video_information['FaceSearchResponse']
        print("face_search_response: ",face_search_response)
        is_known_person_present, known_person_face_id, unknown_person_list = get_unknown_faces_if_known_face_not_present(
            face_search_response)
        if is_known_person_present:
            process_known_visitor(known_person_face_id)
            pass
        elif unknown_person_list:
            # send sms to owner
            fragment_number = video_information["InputInformation"]["KinesisVideo"]["FragmentNumber"]
            print("fragment_number: ",fragment_number)
            process_unknown_visitor(unknown_person_list, fragment_number)
            pass


def get_video_information(kinesis_dict):
    print("get_video_information")
    base64_encoded_data = kinesis_dict['data']
    decoded_data = base64.b64decode(base64_encoded_data)
    return json.loads(decoded_data)


def get_unknown_faces_if_known_face_not_present(face_search_response):
    print("get_unknown_faces_if_known_face_not_present")
    print("face_search_response1: ",face_search_response)
    is_known_person_present = False
    unknown_person_list = []
    if face_search_response:
        for faces in face_search_response:
            if faces['MatchedFaces']:
                # print(json.dumps(faces, indent=2))
                is_known_person_present = True
                unknown_person_list = []
                # change to accept multiple face id's
                face_id = faces['MatchedFaces'][0]['Face']['FaceId']
                return is_known_person_present, face_id, unknown_person_list
            else:
                unknown_person_list.append(faces['DetectedFace'])
    return is_known_person_present, None, unknown_person_list


def process_known_visitor(known_person_face_id):
    print("process_known_visitor")
    is_new_user = check_if_new_user(known_person_face_id)
    if not is_new_user:
        otp = get_random_otp()
        visitor_phone_number = get_visitor_phone_number(known_person_face_id)
        row_identifier = str(uuid.uuid1())
        insert_in_passcode_table(row_identifier, known_person_face_id, otp)
        send_sms_to_visitor(visitor_phone_number, row_identifier, otp)
    else:
        print("OTP already sent to the user")


def check_if_new_user(face_id):
    print("check_if_new_user")
    table = dynamodb_resource.Table('passcodes')
    filtering_exp = Key("faceId").eq(face_id)
    response = table.scan(FilterExpression=filtering_exp)
    print(response)
    return response["Count"] > 0


def get_random_otp():
    print("get_random_otp")
    otp = 0
    for i in range(1, 5):
        otp += random.randint(0, 9)
        otp *= 10
    return otp


def get_visitor_phone_number(face_id):
    print("get_visitor_phone_number")
    item = dynamo_db_client.get_item(TableName='visitors', Key={'faceId': {'S': face_id}})
    print(json.dumps(item, indent=2))
    return item['Item']['phone_number']['S']


def insert_in_passcode_table(row_identifier, known_person_face_id, otp):
    print("insert_in_passcode_table")
    expiry_time = int(time.time()) + 5 * 60
    dynamo_db_client.put_item(TableName='passcodes', Item={'uuid': {'S': row_identifier}
        , 'expiry_time': {'N': str(expiry_time)}
        , 'faceId': {'S': str(known_person_face_id)}
        , 'otp': {'N': str(otp)}
                                                     })


def send_sms_to_visitor(visitor_phone_number, row_identifier, otp):
    print("send_sms_to_visitor")
    message = "Otp : {}\nClick Here: http://smart-door-website.s3-website-us-east-1.amazonaws.com/otp.html?uuid={}".format(
        otp, row_identifier)
    check = sns_client.publish(PhoneNumber=visitor_phone_number,Message=message)
    print("sns response", check)
    SUBJECT = "Your OTP to open the door"
    BODY_TEXT = ("Amazon SES Test (Python)\r\n"
                 "This email was sent with Amazon SES using the "
                 "AWS SDK for Python (Boto)."
                 )
    BODY_HTML = """<html>
                    <head></head>
                    <body>
                      <h1>""" + "Your OTP is {}".format(otp) + """</h1>
                      <p>
                        <a href=""" + "http://smart-door-website.s3-website-us-east-1.amazonaws.com/otp.html?uuid={}".format(
        row_identifier) + """>Click Here</a> using the
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
    # print("ses response", response)


def process_unknown_visitor(unknown_person_list, fragment_number):
    # get frame
    print("process_unknown_visitor")
    row_identifier = str(uuid.uuid1())
    frame_temporary_location = "/tmp/{}".format(row_identifier)
    extract_frame(frame_temporary_location, fragment_number)
    # get base64 of image
    img_file = "{}.jpeg".format(frame_temporary_location)
    is_unknown_visitor_already_processed = check_if_unknown_visitor_already_processed(img_file)
    if not is_unknown_visitor_already_processed:
        base64_string = base64.b64encode(open(img_file, "rb").read()).decode()
        print("base64_string", base64_string)
        base64_encoded_image = "data:image/jpeg;base64,{}".format(base64_string)
        insert_in_unauthorized_table(base64_encoded_image, row_identifier)
        send_sms_to_owner(row_identifier)
        save_image_for_comparision(img_file)
    else:
        print("unknown visitor already processed")


def extract_frame(frame_temporary_location, fragment_number):
    print("extract_frame")
    kvs_data_pt = kvs_client.get_data_endpoint(
        StreamARN="arn:aws:kinesisvideo:us-east-1:888913162450:stream/smartDoorVideoStream/1586228638331",  # kinesis stream arn
        APIName='GET_MEDIA'
    )
    end_pt = kvs_data_pt['DataEndpoint']
    #kvs_video_client = boto3.client('kinesis-video-media', endpoint_url=end_pt, region_name='us-west-2')
    kvs_video_client = boto3.client('kinesis-video-media', endpoint_url=end_pt, region_name='us-east-1')
    kvs_stream = kvs_video_client.get_media(
        StreamARN="arn:aws:kinesisvideo:us-east-1:888913162450:stream/smartDoorVideoStream/1586228638331",  # kinesis stream arn
        StartSelector={'StartSelectorType': 'FRAGMENT_NUMBER', 'AfterFragmentNumber': fragment_number}
        # to keep getting latest available chunk on the stream
    )
    with open("{}.mkv".format(frame_temporary_location), 'wb') as f:
        streamBody = kvs_stream['Payload'].read(
            1024 * 2048)  # reads min(16MB of payload, payload size) - can tweak this
        f.write(streamBody)
        cap = cv2.VideoCapture("{}.mkv".format(frame_temporary_location))
        ret, frame = cap.read()
        all_frames = []
        # print("ret",ret, "****")
        # while ret and len(all_frames)<=20:
        #    print(len(all_frames),"all_frames")
        #    all_frames.append(frame)
        #    ret, frame = cap.read()
        # print(all_frames)
        cv2.imwrite("{}.jpeg".format(frame_temporary_location), frame)
        s3_client = boto3.client('s3')
        s3_client.upload_file(
            "{}.jpeg".format(frame_temporary_location),
            "smart-door-visitor-faces-cc-frames",  # replace with your bucket name
            'frame_{}.jpeg'.format(frame_temporary_location)
        )
        cap.release()


def send_sms_to_owner(row_identifier):
    print("send_sms_to_owner")
    message = "New User Alert!\nhttp://smart-door-website.s3-website-us-east-1.amazonaws.com/unknown-person.html?uuid={}".format(
        row_identifier)
    # print(sns_client.publish(PhoneNumber="+19172028241",Message=message))
    SUBJECT = "New User Alert"
    BODY_TEXT = ("Amazon SES Test (Python)\r\n"
                 "This email was sent with Amazon SES using the "
                 "AWS SDK for Python (Boto)."
                 )
    BODY_HTML = """<html>
                    <head></head>
                    <body>
                      <h1>New user alert</h1>
                      <p>
                        <a href=""" + "'http://smart-door-website.s3-website-us-east-1.amazonaws.com/unknown-person.html?uuid={}'".format(
        row_identifier) + """>Click here</a>
                      </p>
                    </body>
                    </html>
                """
    CHARSET = "UTF-8"
    client = boto3.client('ses')
    response = client.send_email(
        Destination={
            'ToAddresses': [
                "ga1380@nyu.edu",
            ],
        },
        Message={
            'Body': {
                'Html': {
                    'Charset': CHARSET,
                    'Data': BODY_HTML,
                },
                'Text': {
                    'Charset': CHARSET,
                    'Data': message,
                },
            },
            'Subject': {
                'Charset': CHARSET,
                'Data': SUBJECT,
            },
        },
        Source=SENDER)
    print("ses response", response)


def insert_in_unauthorized_table(base64_encoded_image, row_identifier):
    print("insert_in_unauthorized_table")
    expiry_time = int(time.time()) + 1 * 300
    dynamo_db_client.put_item(TableName='unauthorized_visitors', Item={'uuid': {'S': row_identifier}
        , 'ttl': {'N': str(expiry_time)}
        , 'base64_encoded_image': {'S': base64_encoded_image}
                                                                       })


def check_if_unknown_visitor_already_processed(img_file):
    print("check_if_unknown_visitor_already_processed")
    table = dynamodb_resource.Table('unauthorized_visitors')
    filtering_exp = Key("ttl").gte(int(time.time()))
    response = table.scan(FilterExpression=filtering_exp)
    print(response)
    return response["Count"] > 0


def save_image_for_comparision(img_file):
    print("save_image_for_comparision")
    s3_client = boto3.client('s3')
    s3_client.upload_file(
        img_file,
        "smart-door-visitor-faces-cc-compare-face",  # replace with your bucket name
        'destination_compare.jpeg'
    )
