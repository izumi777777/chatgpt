import os
import sys
import logging
import openai
import boto3
import time
import json

from datetime import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import LineBotApiError, InvalidSignatureError

logger = logging.getLogger()
logger.setLevel(logging.ERROR)

# 環境変数からLINEBotのチャンネルアクセストークンとシークレットを読み込む
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
openai.api_key = os.getenv("OPENAI_API_KEY")

# トークンが確認できない場合エラーを出力して終了
if channel_secret is None:
    logger.error('Specify LINE_CHANNEL_SECRET as an environment variable.')
    sys.exit(1)
if channel_access_token is None:
    logger.error('Specify LINE_CHANNEL_ACCESS_TOKEN as an environment variable.')
    sys.exit(1)

# LineBot APIとWebhookHandlerの生成（チャンネルアクセストークンとシークレットを渡す）
line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# # DynamoDBクライアントの生成
# dynamodb = boto3.resource('dynamodb')
# table_name = 'chatgpthistory-table'  # DynamoDBテーブル名
# table = dynamodb.Table(table_name)

# SQSクライアントの生成
sqs = boto3.client('sqs')
queue_url = 'https://sqs.ap-northeast-1.amazonaws.com/355126125825/est-lambda-message-sqs'  # SQSキューのURL

# Lambdaのメインの動作
def lambda_handler(event, context):
    # 認証用のx-line-signatureヘッダー
    signature = event["headers"]["x-line-signature"]
    body = event["body"]

    # レスポンスの設定
    ok_json = {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {},
        "body": ""
    }
    error_json = {
        "isBase64Encoded": False,
        "statusCode": 500,
        "headers": {},
        "body": "Error"
    }

    # LINEからのメッセージをSQSキューに送信
    def send_message_to_sqs(line_event, response_text, cost):
        user_id = line_event.source.user_id
        text = line_event.message.text

        message = {
            'user_id': user_id,
            'text': text,
            'response_text': response_text,
            'cost': cost
        }

        # メッセージをJSON形式でシリアライズしてSQSキューに送信
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message)
        )

    # LINEからのメッセージを処理するハンドラー
    @handler.add(MessageEvent, message=TextMessage)
    def message_handler(line_event):
        # SQSキューにメッセージを送信
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": line_event.message.text}
            ]
        )
        
        # レスポンスと料金を取得して返信メッセージとして送信
        response_text = completion.choices[0].message.content
        cost = completion['usage']['total_tokens']
        cost = cost / 100  # コストを小数点に変換する
        send_message_to_sqs(line_event, response_text, cost)

        line_bot_api.reply_message(
            line_event.reply_token,
            TextSendMessage(text=f"{response_text}")
        )

        #受信したテキストをCloudWatchLogsに出力する
        print(completion.choices[0].message.content)
        text=completion.choices[0].message.content.lstrip()

        # レスポンスと料金をログに出力
        logger.info("Response: %s" % response_text)
        logger.info("Cost: %s" % cost)
        logger.info("text: %s" % text)

        # レスポンスと料金をレスポンスデータに設定
        ok_json["body"] = {
            "response": response_text,
            "cost": cost
        }
        
    # 例外処理
    try:
        handler.handle(body, signature)
        return ok_json  # レスポンスを返す
    except LineBotApiError as e:
        logger.error("Got exception from LINE Messaging API: %s\n" % e.message)
        for m in e.error.details:
            logger.error("  %s: %s" % (m.property, m.message))
        return error_json  # エラーレスポンスを返す
    