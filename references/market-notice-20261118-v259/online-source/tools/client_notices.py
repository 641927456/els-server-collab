"""Read notice policy through the existing pinned, authenticated TLS channel."""
import asyncio
import hashlib
import json
from pathlib import Path
import threading

from els_server.friends_bridge import Bridge
from els_server.friends_wire import read_json
from els_server.domain.client_notices import validate

CLIENT_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'


async def fetch(config):
    bridge = Bridge(config)
    writer = None
    try:
        async with asyncio.timeout(12):
            reader, writer = await bridge.remote('client-notices')
            value = await read_json(reader)
            if set(value) != {'enabled', 'text', 'revision'}:
                raise ValueError('客户端提示响应字段无效')
            settings = validate({key: value[key] for key in ('enabled', 'text')})
            expected = hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if value['revision'] != expected:
                raise ValueError('客户端提示版本不匹配')
            return value
    finally:
        if writer is not None:
            await bridge._close_writer(writer)


class NoticeSync:
    def __init__(self, config, script, initial, report):
        self.config, self.script, self.report = config, script, report
        self.revision = initial['revision']
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, name='client-notice-sync', daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        while not self.stopped.wait(30):
            try:
                value = asyncio.run(fetch(self.config))
                if self.stopped.is_set():
                    return
                if value['revision'] != self.revision:
                    self.script.exports_sync.configure(value)
                    self.revision = value['revision']
                self.report['client_notice_revision'] = self.revision
                self.report.pop('client_notice_sync_error', None)
            except Exception as error:
                # Keep the last authenticated policy; expose failure instead of
                # claiming that the newest GM setting reached this client.
                self.report['client_notice_sync_error'] = type(error).__name__
                print('CLIENT_NOTICE_SYNC_ERROR: ' + type(error).__name__, flush=True)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=18)


def source(client_sha256, initial):
    if client_sha256 != CLIENT_SHA:
        raise ValueError('客户端内置提示组件不支持此游戏版本')
    return Path(__file__).with_suffix('.js').read_text('utf8').replace('__INITIAL_POLICY__', json.dumps(initial))
