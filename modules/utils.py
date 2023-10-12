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


def check_repetitive_string(input_string):
    """
    Check if the same text is repeated 2 or more times
    """
    # Remove numbers and newline characters from the input string
    input_string = re.sub(r"\d+", "", input_string).replace("\n", "")

    for i in range(1, len(input_string) // 2 + 1):
        pattern = "(.{" + str(i) + ",}?)\\1{1,}"
        match = re.search(pattern, input_string)
        if match:
            return True
    return False
