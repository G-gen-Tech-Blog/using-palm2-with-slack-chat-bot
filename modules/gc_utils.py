from google.cloud import secretmanager
from googleapiclient import discovery
from google.cloud import storage
from google.cloud.storage import Blob
from google.auth import default
from modules import utils


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


def download_blob(bucket_name: str, source_blob_name: str) -> Blob:
    """
    google cloud storageからオブジェクトをダウンロード

    Parameters
    ----------
    bucket_name : str
        バケット名 (gs://を除き)
    source_blob_name: str
        ファイル名
    payload : str
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    return blob


def upload_blob(bucket_name: str, python_object, destination_blob_name: str):
    """
    データをGoogle Cloud Storageへアップロード
    """
    pickle_object = utils.serialize_to_pickle(python_object)
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(pickle_object)


def get_keyword(text_model, prompt: str, parameters) -> str:
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
    response = text_model.predict(get_keyword_prompt, **parameters)
    is_blocked = response.is_blocked
    if is_blocked:
        keyword = "入力または出力が Google のポリシーに違反している可能性があるため、出力がブロックされています。プロンプトの言い換えや、パラメータ設定の調整を試してください。現在、英語にのみ対応しています。"
    else:
        keyword = utils.remove_markdown(response.text)
    return keyword


def send_log(logger, user_id: str, prompt: str, payload: str, keyword: str) -> None:
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

    # ログに書き込むデータを持つ辞書を作成する
    data = {
        "slack_user_id": user_id,
        "prompt": prompt,
        "response": payload,
        "keyword": keyword,
    }

    # 辞書をJSON文字列に変換する
    logger.log_struct(data)


def store_historical_chat_to_gcs(
    metadata_chat: str,
    historical_chat: list,
    historical_chat_bucket_name: str,
    historical_chat_blob_name: str,
):
    """
    google cloud storageへcontext及びチャット履歴を保存

    """
    historical_chat = {
        "metadata_chat": metadata_chat,
        "historical_chat": historical_chat,
    }
    upload_blob(
        historical_chat_bucket_name,
        historical_chat,
        historical_chat_blob_name,
    )
