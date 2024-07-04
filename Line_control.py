from fastapi import FastAPI, Request, Response, status
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)
import os
from server import selectFromDB,initDB,prompt

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

config = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration=config)
messaging_api = MessagingApi(api_client)
handler = WebhookHandler(CHANNEL_SECRET)

conn, cursor = initDB()

async def handle_webhook(request: Request):
    # 獲取請求頭中的 X-Line-Signature
    signature = request.headers.get('X-Line-Signature')

    # 獲取請求體作為字串
    body = await request.body()
    try:
        # 處理 Webhook 事件
        handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    return Response(status_code=status.HTTP_200_OK)

def handle_message(event):
    print(event.message.text)
   
    profile = selectFromDB(conn, "llm_twins", "name", prompt.role)
    
    reply_token = event.reply_token
    reply_text = prompt(profile,event.message.text)
    
    reply_message = ReplyMessageRequest(
        reply_token=reply_token,
        messages=[TextMessage(text=reply_text)]
    )
    messaging_api.reply_message(reply_message)
    
@handler.add(MessageEvent, message=TextMessageContent)    
def handle_message(event):
    with ApiClient(config) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=event.message.text)]
            )
        )