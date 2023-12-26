from fastapi import FastAPI, Request
from google.cloud import logging

from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from slack_sdk.web.async_client import AsyncWebClient

import vertexai
from vertexai.language_models import TextGenerationModel

from modules import gc_utils, utils

# Secret Managerから環境変数を読み込む（Secret Managerを使わなければ１．事前に環境変数にこれらの値を格納し、環境変数から読み込む。２.ハードコードで入力。）
PROJECT_ID, PROJECT_NO = gc_utils.get_project_number()
SIGNING_SECRET = gc_utils.access_secret_version(
    PROJECT_NO, "palm2-slack-chatbot-l-signing-secret"
)
SLACK_TOKEN = gc_utils.access_secret_version(
    PROJECT_NO, "palm2-slack-chatbot-l-slack-token"
)
RESOURCE_LOCATION = "us-central1"

HISTORICAL_CHAT_BUCKET_NAME = "historical-chat-object"

# FastAPI
app = App(token=SLACK_TOKEN, signing_secret=SIGNING_SECRET)
app_handler = SlackRequestHandler(app)
api = FastAPI()


@api.post("/slack/events")
async def endpoint(req: Request):
    return await app_handler.handle(req)


# VertexAIを初期化
vertexai.init(project=PROJECT_ID, location=RESOURCE_LOCATION)

text_model = TextGenerationModel.from_pretrained("text-bison")
PARAMETERS = {
    "max_output_tokens": 1024,
    "temperature": 0.20,
    "top_p": 0.95,
    "top_k": 40,
}

RESPONSE_STYLE = """"""

# cloud logging
logging_client = logging.Client()

# cloud logging: 書き込むログの名前
logger_name = "palm2_slack_chatbot"

# cloud logging: ロガーを選択する
logger = logging_client.logger(logger_name)

# 本動作はここから


def generate_response(
    client: AsyncWebClient,
    ts: str,
    conversation_thread: str,
    user_id: str,
    channel_id: str,
    prompt: str,
) -> None:
    """
    ユーザーIDがボットのIDまたはNoneでなく、かつチャンネルIDが存在する場合、Slackチャンネルにメッセージを投稿する。

    Parameters
    ----------
    ts : str
        メッセージのタイムスタンプ
    user_id : str
        ユーザーID
    channel_id : str
        チャンネルID
    prompt : str
        プロンプト
    """
    response = text_model.predict(prompt, **PARAMETERS)

    # ブロックされたか確認する
    is_blocked = response.is_blocked
    is_empty_response = len(response.text.strip(" \n")) < 1

    if is_blocked or is_empty_response:
        payload = "入力または出力が Google のポリシーに違反している可能性があるため、出力がブロックされています。プロンプトの言い換えや、パラメータ設定の調整を試してください。"
    else:
        # slackで**などのmarkdownを正しく表示できないので削除し、簡潔にする
        payload = utils.remove_markdown(response.text)

    # レスポンスをslackへ返す
    client.chat_postMessage(channel=channel_id, thread_ts=ts, text=payload)

    keyword = gc_utils.get_keyword(text_model, prompt, PARAMETERS)
    gc_utils.send_log(logger, user_id, prompt, payload, keyword)


@app.event("message")
def handle_incoming_message(client: AsyncWebClient, payload: dict) -> None:
    """
    受信メッセージを処理する

    Parameters
    ----------
    payload : dict
        ペイロード
    """
    channel_id = payload.get("channel")
    user_id = payload.get("user")
    prompt = payload.get("text")
    ts = payload.get("ts")
    thread_ts = payload.get("thread_ts")
    conversation_thread = ts if thread_ts is None else thread_ts
    generate_response(client, ts, conversation_thread,
                      user_id, channel_id, prompt)
