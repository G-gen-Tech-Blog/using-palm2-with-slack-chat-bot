import json
import re

from flask import Flask
from google.auth import default
from google.cloud import logging
from google.cloud import secretmanager
from googleapiclient import discovery
import slack
from slackeventsapi import SlackEventAdapter

import vertexai
from vertexai.language_models import TextGenerationModel


def get_project_number() -> tuple:
    """
    プロジェクトの番号を取得する

    Returns
    ----------
    tuple
        プロジェクトのIDと番号
    """
    credentials, project_id = default()
    service = discovery.build("cloudresourcemanager", "v1", credentials=credentials)
    project = service.projects().get(projectId=project_id).execute()
    return project_id, project["projectNumber"]


def access_secret_version(
    project_id: str, secret_id: str, version_id: str = "latest"
) -> str:
    """
    最新バージョンの秘密の内容をデコードする

    Parameters
    ----------
    project_id : str
        プロジェクトのID
    secret_id : str
        シークレットのID
    version_id : str
        バージョンのID（最新バージョンがデフォルト）

    Returns
    ----------
    str
        デコードしたシークレットの値
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("UTF-8")


# 環境変数を読み込む
PROJECT_ID, PROJECT_NO = get_project_number()
SIGNING_SECRET = access_secret_version(
    PROJECT_NO, "palm2-slack-chatbot-l-signing-secret"
)
SLACK_TOKEN = access_secret_version(PROJECT_NO, "palm2-slack-chatbot-l-slack-token")
RESOURCE_LOCATION = "us-central1"

# Flask
app = Flask(__name__)

# Slack
slack_event_adapter = SlackEventAdapter(SIGNING_SECRET, "/slack/events", app)
slack_client = slack.WebClient(token=SLACK_TOKEN)
BOT_ID = slack_client.api_call("auth.test")["user_id"]

# VertexAIを初期化
vertexai.init(project=PROJECT_ID, location=RESOURCE_LOCATION)

parameters = {"temperature": 0.2, "max_output_tokens": 1024, "top_p": 0.8, "top_k": 20}
model = TextGenerationModel.from_pretrained("text-bison@001")

# Local cache (スケールアップするとき、memorystoreへ移行する必要)
handled_events = {}

# cloud logging
logging_client = logging.Client()

# cloud logging: 書き込むログの名前
logger_name = "palm2_slack_chatbot"

# cloud logging: ロガーを選択する
logger = logging_client.logger(logger_name)


def remove_markdown(text):
    # インラインコードブロックを削除する
    text = re.sub(r"`(.+?)`", r"\1", text)
    # マルチラインコードブロックを削除する
    text = re.sub(r"```(.+?)```", r"\1", text)
    # ボールドマークダウンを削除する
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # イタリックマークダウンを削除する
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # ヘッダーマークダウンを---で置き換える
    text = re.sub(r"^#{1,6}\s*(.+)", r"---\1---", text, flags=re.MULTILINE)
    return text


def get_keyword(prompt: str) -> str:
    """
    キーワードを取得する

    Parameters
    ----------
    prompt : str
        プロンプト

    Returns
    ----------
    str
        キーワード
    """
    get_keyword_prompt = f"""勉強会の計画

    以下の文章からテーマまたコンテキストとなるキーワードを1つ生成してください: サボテンの育て方
    コンテンツの消費者は、サボテンの育て方に興味がある人々
    サボテンは、初心者でも育てやすい植物です。しかし、サボテンを健康に育てるためには、いくつかの注意点があります。
    サボテンの育て方について、以下の点を教えてください。
    - サボテンの種類
    - サボテンの土
    - サボテンの水やり
    - サボテンの肥料
    - サボテンの剪定
    - サボテンの病気と害虫
    テーマまたコンテキストとなるキーワード: サボテンの育て方

    以下の文章からテーマまたコンテキストとなるキーワードを1つ生成してください: 鍼灸学において、よだれつわりの治療法を教えてください。また、理由と考え方も教えてください。読み手は鍼灸師だとします。鍼を打つべきなツボとその理由を詳しく教えてください
    テーマまたコンテキストとなるキーワード: 鍼灸学医療

    以下の文章からテーマまたコンテキストとなるキーワードを1つ生成してください: 金融業界のビジネスプラン
    金融業界のビジネスプランを作成してください。
    ビジネスプランには、以下の項目を含めてください。
    - 会社の概要
    - 製品やサービスの概要
    - 市場分析
    - 競合分析
    - マーケティング戦略
    - 財務計画
    ビジネスプランは、3年間で利益を出すことを目標としてください。
    テーマまたコンテキストとなるキーワード: ビジネスプランの作成

    以下の文章からテーマまたコンテキストとなるキーワードを1つ生成してください: 30代男性向けのマーケティングのアイディアを教えてください
    テーマまたコンテキストとなるキーワード: マーケティング戦略

    以下の文章からテーマまたコンテキストとなるキーワードを1つ生成してください: {prompt}
    テーマまたコンテキストとなるキーワード:
    """
    response = model.predict(get_keyword_prompt, **parameters)
    is_blocked = response.is_blocked
    if is_blocked:
        keyword = "入力または出力が Google のポリシーに違反している可能性があるため、出力がブロックされています。プロンプトの言い換えや、パラメータ設定の調整を試してください。現在、英語にのみ対応しています。"
    else:
        keyword = remove_markdown(response.text)
    return keyword


def send_log(user_id: str, prompt: str, payload: str) -> None:
    """
    ログを送信する

    Parameters
    ----------
    user_id : str
        ユーザーID
    prompt : str
        プロンプト
    payload : str
        ペイロード
    """
    keyword = get_keyword(prompt)
    # ログに書き込むデータを持つ辞書を作成する
    data = {
        "slack_user_id": user_id,
        "prompt": prompt,
        "response": payload,
        "keyword": keyword,
    }

    # 辞書をJSON文字列に変換する
    json_data = json.dumps(data)
    logger.log_struct(json.loads(json_data))


def post_message_if_not_from_bot(
    ts: str, user_id: str, channel_id: str, prompt: str
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
    is_handled_event = ts == handled_events.get(f"{channel_id}_{user_id}")
    is_bot_or_invalid = user_id in (BOT_ID, None)

    if not is_handled_event and not is_bot_or_invalid:
        handled_events[f"{channel_id}_{user_id}"] = ts
        slack_client.chat_postMessage(
            channel=channel_id, thread_ts=ts, text="...処理中..."
        )
        response = model.predict(prompt, **parameters)
        is_blocked = response.is_blocked
        if is_blocked:
            payload = "入力または出力が Google のポリシーに違反している可能性があるため、出力がブロックされています。プロンプトの言い換えや、パラメータ設定の調整を試してください。現在、英語にのみ対応しています。"
        else:
            payload = remove_markdown(response.text)
        slack_client.chat_postMessage(channel=channel_id, thread_ts=ts, text=payload)
        send_log(user_id, prompt, payload)


@slack_event_adapter.on("message")
def handle_incoming_message(payload: dict) -> None:
    """
    受信メッセージを処理する

    Parameters
    ----------
    payload : dict
        ペイロード
    """
    event = payload.get("event", {})
    channel_id = event.get("channel")
    user_id = event.get("user")
    prompt = event.get("text")
    ts = event.get("ts")

    post_message_if_not_from_bot(ts, user_id, channel_id, prompt)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
