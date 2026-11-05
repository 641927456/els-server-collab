"""DX11 3C9 -> BAD290 -> CX2NoticeManager::queue (7ABD10).

The native reader consumes Q, sender wstring, text wstring. Empty sender
selects system notice, queue category 0 and repeat flag 1. Witness and offline
replay live in the GM candidate's notice-native report.
"""
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event


def scrolling_notice(text):
    if (not isinstance(text,str) or not text.strip() or len(text)>200
            or any(ord(c)<32 or ord(c)==127 for c in text)
            or any(c in text for c in '<>')):
        raise ValueError('公告需要 1–200 字，不允许控制字符或富文本标签')
    if len(text.encode('utf-16le'))>800:raise ValueError('公告超出原生字符串边界')
    return Event(0x201,kind=0x3c9,payload=bytes(8)+wstring('')+wstring(text))
