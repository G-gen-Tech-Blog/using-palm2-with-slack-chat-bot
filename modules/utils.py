import re
import pickle


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
    return text.replace("[Example]:", "")


def serialize_to_pickle(python_object):
    """
    Pythonのデータをシリアル化
    """
    serialized_object = pickle.dumps(python_object)
    return serialized_object
