import json
import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table_name = 'chatgpthistory-table'  # DynamoDBテーブル名
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    for record in event['Records']:
        message_body = json.loads(record['body'])
        user_id = message_body['user_id']
        text = message_body['text']
        response_text = message_body['response_text']
        cost = message_body['cost']

        # DynamoDBに会話履歴を保存
        save_chat_history(user_id, text, response_text, cost)

    return {
        'statusCode': 200,
        'body': 'Processed all messages'
    }

# DynamoDBに書き込み
def save_chat_history(user_id, input_text, response_text, cost):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    item = {
        'UserId': user_id,
        'Timestamp': current_time,
        'InputText': input_text,
        'ResponseText': response_text,
        'Cost': str(cost) + "円"
    }
    table.put_item(Item=item)
