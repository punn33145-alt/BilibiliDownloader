import sys

sys.path.insert(0, r"D:\Download_VD_Bilibili")

from app.core.url_validator import is_valid_bilibili_url

assert is_valid_bilibili_url("[SSL: CERTIFICATE_VERIFY_FAILED] certificate") is False

assert is_valid_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD") is True

print("url_validator OK")

