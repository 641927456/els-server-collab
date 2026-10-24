"""Loopback-only desktop UI host. No network-facing GM endpoint."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from launcher.service import LauncherService, ROOT, psutil
from els_server.storage.lifecycle import SaveLease


def open_window(url, home):
    if os.name == 'nt':
        paths = [Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',
                 Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Google/Chrome/Application/chrome.exe']
        for exe in paths:
            if exe.is_file():
                subprocess.Popen([str(exe), '--app='+url, '--window-size=1280,860',
                                  '--user-data-dir='+str(home/'browser'), '--no-first-run',
                                  '--disable-background-mode'], creationflags=subprocess.CREATE_NO_WINDOW)
                return
    webbrowser.open(url)


def browser_alive(home):
    """A minimized/sleeping app window must not lose its local UI host."""
    profile = str((home/'browser').resolve()).casefold()
    for process in psutil.process_iter(['name','cmdline']):
        try:
            if (process.info['name'] or '').lower() not in ('msedge.exe','chrome.exe'):
                continue
            args = process.info['cmdline'] or []
            if any(a.startswith('--type=') for a in args):
                continue
            if any(a.startswith('--user-data-dir=') and str(Path(a.split('=',1)[1]).resolve()).casefold() == profile for a in args):
                return True
        except (psutil.Error, OSError):
            continue
    return False


class LauncherHTTP(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, service, port=0):
        super().__init__(('127.0.0.1', port), Handler)
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.url = self.origin+'/?view='+os.environ.get('ELS_LOCAL_MANAGER_VIEW','gm')+'#'+self.token
        self.heartbeat = time.monotonic()
        self.ui_seen = False
        self.close_requested = False
        self.native_window = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log URL fragments or authorization headers.

    def headers_for(self, status, mime, size):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(size))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()

    def respond(self, obj, status=200):
        blob = json.dumps(obj, ensure_ascii=False).encode('utf8')
        self.headers_for(status, 'application/json; charset=utf-8', len(blob))
        self.wfile.write(blob)

    def authorized(self):
        if self.headers.get('Host') != self.server.origin.removeprefix('http://'):
            return False
        return hmac.compare_digest(self.headers.get('X-Launcher-Token', ''), self.server.token)

    def do_GET(self):
        route = urllib.parse.urlsplit(self.path)
        path = route.path
        if self.headers.get('Host') != self.server.origin.removeprefix('http://'):
            return self.respond(dict(error='Invalid host'), 403)
        if not path.startswith('/api/'):
            name = {'/':'index.html', '/index.html':'index.html', '/app.js':'app.js',
                    '/style.css':'style.css', '/favicon.svg':'favicon.svg'}.get(path)
            if path.startswith('/assets/') and Path(path).name in {'ruben.webp','elsword.webp','eve.webp','elsword-portrait.webp'}:
                name = 'assets/'+Path(path).name
            if not name:
                return self.respond(dict(error='Not found'), 404)
            target = Path(__file__).parent/name
            if not target.is_file():
                return self.respond(dict(error='Missing UI asset'), 404)
            blob = target.read_bytes()
            mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            if name.endswith(('.html','.js','.css','.svg')):
                mime += '; charset=utf-8'
            self.headers_for(200, mime, len(blob)); self.wfile.write(blob)
            return
        if not self.authorized():
            return self.respond(dict(error='会话已失效，请重新打开启动器'), 401)
        service = self.server.service
        params = urllib.parse.parse_qs(route.query)
        try:
            if path == '/api/state':
                self.server.heartbeat = time.monotonic(); self.server.ui_seen = True
                result = service.state()
                result['native_window'] = self.server.native_window is not None
                result['maximized'] = bool(self.server.native_window and self.server.native_window.maximized)
            elif path == '/api/characters': result = service.characters()
            elif path == '/api/inventory': result = service.inventory(int(params.get('uid',['0'])[0]))
            elif path == '/api/items': result = service.search_items(params.get('q',[''])[0], params.get('group',['all'])[0], int(params.get('offset',['0'])[0]))
            elif path == '/api/backups': result = service.backup_list()
            elif path == '/api/history': result = service.history()
            elif path == '/api/logs': result = service.logs()
            elif path == '/api/features': result = service.features()
            else: return self.respond(dict(error='Not found'), 404)
            self.respond(dict(data=result))
        except (ValueError, RuntimeError) as e:
            self.respond(dict(error=str(e)), 409)
        except Exception as e:
            self.respond(dict(error='读取失败：'+str(e)), 500)

    def do_POST(self):
        if not self.authorized() or self.headers.get('Origin') != self.server.origin:
            return self.respond(dict(error='本地会话验证失败，请重新打开启动器'), 403)
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.respond(dict(error='请求格式错误'), 415)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 16384:
                raise ValueError('请求大小超出限制')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('无效请求')
            service = self.server.service
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/start': result = service.start()
            elif path == '/api/stop': result = service.stop()
            elif path == '/api/check': result = service.check()
            elif path == '/api/gm': result = service.mutate(data)
            elif path == '/api/backup': result = service.backup()
            elif path == '/api/open': result = service.open_folder(data.get('which'))
            elif path == '/api/window':
                if not self.server.native_window:raise ValueError('当前窗口未使用原生容器')
                result = self.server.native_window.action(data.get('action'))
            elif path == '/api/close':
                self.server.heartbeat = 0
                self.server.close_requested = True
                if self.server.native_window:self.server.native_window.action('close')
                result = dict(message='启动器已关闭；运行中的游戏会继续，退出后自动结束服务')
            else: return self.respond(dict(error='Not found'), 404)
            self.respond(dict(data=result))
        except (ValueError, RuntimeError) as e:
            self.respond(dict(error=str(e)), 409)
        except Exception as e:
            self.respond(dict(error='操作失败：'+str(e)), 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--save', type=Path, help='Isolated validation database; launching is disabled')
    args = parser.parse_args()
    service = LauncherService(save=args.save.resolve() if args.save else None)
    runtime = service.home/'runtime.json'
    lease = SaveLease(service.home/'instance')
    try:
        lease.__enter__()
    except RuntimeError:
        if runtime.exists() and not args.headless:
            previous=json.loads(runtime.read_text(encoding='utf8'))
            if previous.get('native'):
                origin,token=previous['url'].split('/#')
                request=urllib.request.Request(origin+'/api/window',data=b'{"action":"restore"}',
                    headers={'X-Launcher-Token':token,'Content-Type':'application/json','Origin':origin})
                with urllib.request.urlopen(request,timeout=5):pass
            else:
                open_window(previous['url'],service.home)
            return 0
        raise SystemExit('启动器已经运行')
    try:
        server = LauncherHTTP(service, args.port)
        runtime.write_text(json.dumps(dict(url=server.url,pid=os.getpid(),native=not args.headless), ensure_ascii=False), encoding='utf8')
        if sys.stdout:
            print(server.origin, flush=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            if not args.headless:
                from launcher.native_window import NativeWindow
                server.native_window=NativeWindow(server,service.home)
                server.native_window.run()
            while True:
                time.sleep(1)
                age = time.monotonic()-server.heartbeat
                # Keep ownership while the game/check/GM thread is active, even
                # if the user closes the browser's native titlebar button.
                with service.lock:
                    active = service.phase in ('checking','starting','running','stopping') or service.process and service.process.poll() is None
                    if server.close_requested and not active:
                        break
                    if not args.headless and age > (45 if server.ui_seen else 120) and not active and not (server.native_window and server.native_window.alive):
                        break
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown(); server.server_close()
            runtime.unlink(missing_ok=True)
    finally:
        lease.__exit__(None,None,None)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
