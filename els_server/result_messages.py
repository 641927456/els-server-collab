"""Pinned client result-code text; success/failure semantics belong to each handler."""
import functools,hashlib,json
from els_server.game_data import DATA_DIR,CLIENT_SHA


class ResultMessages:
    def __init__(self,directory=DATA_DIR):
        raw=(directory/'result_messages.json').read_bytes()
        self.manifest=json.loads((directory/'result_messages.manifest.json').read_text(encoding='utf8'))
        m=self.manifest
        if m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or m['count']!=3150 or hashlib.sha256(raw).hexdigest()!=m['sha256']:raise ValueError('Result message catalog identity')
        data=json.loads(raw);rows=data['messages']
        if [r['code'] for r in rows]!=list(range(3150)) or any(not isinstance(r['text'],str) for r in rows):raise ValueError('Result message coverage')
        self._texts=tuple(r['text'] for r in rows);self._fallback=data['fallback']['text']
        if not isinstance(self._fallback,str):raise ValueError('Result fallback type')

    def text(self,code):
        if type(code) is not int or not -(2**31)<=code<2**31:raise ValueError('Native result code')
        return self._texts[code] if 0<=code<len(self._texts) else self._fallback


@functools.lru_cache(maxsize=1)
def result_messages():return ResultMessages()
