import json
import pickle

from google.cloud import logging
import vertexai
from vertexai.language_models import ChatModel, InputOutputTextPair, TextGenerationModel

from modules import gc_utils, utils

from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from slack_sdk import WebClient

# 環境変数を読み込む
PROJECT_ID, PROJECT_NO = gc_utils.get_project_number()
SIGNING_SECRET = gc_utils.access_secret_version(
    PROJECT_NO, "palm2-slack-chatbot-l-signing-secret"
)
SLACK_TOKEN = gc_utils.access_secret_version(
    PROJECT_NO, "palm2-slack-chatbot-l-slack-token"
)
RESOURCE_LOCATION = "us-central1"

HISTORICAL_CHAT_BUCKET_NAME = "historical-chat-object"

# Flask

app = App(token=SLACK_TOKEN, signing_secret=SIGNING_SECRET)
app_handler = SlackRequestHandler(app)


from fastapi import FastAPI, Request

api = FastAPI()


@api.post("/slack/events")
async def endpoint(req: Request):
    return await app_handler.handle(req)


slack_client = WebClient(token=SLACK_TOKEN)


# VertexAIを初期化
vertexai.init(project=PROJECT_ID, location=RESOURCE_LOCATION)

chat_model = ChatModel.from_pretrained("chat-bison@001")
text_model = TextGenerationModel.from_pretrained("text-bison@001")
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


sample_raws = []


# 入力出力例を準備
with open("./samples/sample_input-output_pairs.jsonl", "r", encoding="utf-8-sig") as f:
    for line in f:
        sample_raws.append(json.loads(line))

examples = []
for item in sample_raws:
    example_pair = InputOutputTextPair(
        input_text=item["input_text"],
        output_text=item["output_text"],
    )
    examples.append(example_pair)


# 本動作はここから


def post_message_if_not_from_bot(
    ts: str, conversation_thread: str, user_id: str, channel_id: str, prompt: str
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

    # google cloud storage で保存したチャット履歴のオブジェクト名を指定
    historical_chat_blob_name = f"{conversation_thread}.pkl"

    # google cloud storage で保存したチャット履歴のオブジェクトを取得
    historical_chat_blob = gc_utils.download_blob(
        HISTORICAL_CHAT_BUCKET_NAME, historical_chat_blob_name
    )
    is_existing_thread = historical_chat_blob.exists()
    if is_existing_thread:
        # チャット履歴が存在すれば、過去のチャット履歴をダウンロードし、chat_model に投入し、チャットのセッション再開

        serialized_historical_chat = historical_chat_blob.download_as_bytes()
        # 履歴のオブジェクトを逆シリアル化
        historical_chat = pickle.loads(serialized_historical_chat)
        this_prompt_context = f"{RESPONSE_STYLE}"
        # 過去のcontext及びチャット履歴を引数にチャット開始のオブジェクトを作成し、チャットのセッション再開
        chat = chat_model.start_chat(
            context=this_prompt_context,
            examples=examples,
            message_history=historical_chat["historical_chat"],
        )
    else:
        # チャット履歴が存在しなければ、チャット履歴がない状態で新しいチャットセッションを作成
        this_prompt_context = f"{RESPONSE_STYLE}"
        # 生成したcontext及を引数にチャット開始のオブジェクトを作成し、チャットのセッション開始
        chat = chat_model.start_chat(context=this_prompt_context, examples=examples)

    response = chat.send_message(prompt, **PARAMETERS)

    # ブロックされたか確認する
    is_blocked = response.is_blocked
    is_empty_response = len(response.text.strip(" \n")) < 1

    if is_blocked or is_empty_response:
        payload = "入力または出力が Google のポリシーに違反している可能性があるため、出力がブロックされています。プロンプトの言い換えや、パラメータ設定の調整を試してください。"
    else:
        # slackで**などのmarkdownを正しく表示できないので削除し、簡潔にする
        payload = utils.remove_markdown(response.text)

    # レスポンスをslackへ返す
    slack_client.chat_postMessage(channel=channel_id, thread_ts=ts, text=payload)

    gc_utils.store_historical_chat_to_gcs(
        """dummy_metadata_chat""",
        chat._message_history,
        HISTORICAL_CHAT_BUCKET_NAME,
        historical_chat_blob_name,
    )

    if not is_existing_thread:
        keyword = gc_utils.get_keyword(text_model, prompt, PARAMETERS)
        gc_utils.send_log(logger, user_id, prompt, payload, keyword)


@app.event("message")
def handle_incoming_message(payload: dict) -> None:
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
    post_message_if_not_from_bot(ts, conversation_thread, user_id, channel_id, prompt)
