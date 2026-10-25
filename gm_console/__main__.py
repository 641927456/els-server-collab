"""python -m gm_console --config config/friends-server.toml --home state/gm"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit,parse_qs
from gm_console.service import Service
from els_server.storage.lifecycle import SaveLease

STATIC=Path(__file__).parent/'static'


def handler(service):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def reply(self,status,body,kind='application/json; charset=utf-8'):
            if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(body)
        def host_ok(self):
            ports=getattr(self.server,'gm_forwarded_ports',{self.server.server_port})
            return self.headers.get('Host') in {f'{host}:{port}' for host in ('127.0.0.1','localhost') for port in ports}
        def authorized(self):
            return self.host_ok() and hmac.compare_digest(self.headers.get('X-GM-Key','').encode('utf8'),service.key.encode('ascii'))
        def do_GET(self):
            if not self.host_ok():return self.reply(403,dict(error='不允许此访问地址'))
            path=urlsplit(self.path).path
            if path.startswith('/api/'):
                if not self.authorized():return self.reply(401,dict(error='请输入管理访问密钥'))
                try:
                    if path=='/api/status':data=service.status()
                    elif path=='/api/history':data=service.history()
                    elif path=='/api/coupon-rewards':data=service.coupon_read('coupon-rewards')
                    elif path=='/api/coupon-list':
                        q=parse_qs(urlsplit(self.path).query)
                        data=service.coupon_read('coupon-list',dict(offset=int(q.get('offset',['0'])[0])))
                    elif path=='/api/coupon-operation':
                        q=parse_qs(urlsplit(self.path).query)
                        data=service.coupon_read('coupon-operation',dict(operation_id=q.get('operation_id',[''])[0],action=q.get('action',[''])[0]))
                    elif path=='/api/cash-balance':
                        q=parse_qs(urlsplit(self.path).query)
                        data=service.cash_read('cash-balance',dict(account_id=int(q.get('account_id',['0'])[0])))
                    elif path=='/api/cash-operation':
                        q=parse_qs(urlsplit(self.path).query)
                        data=service.cash_read('cash-operation',dict(account_id=int(q.get('account_id',['0'])[0]),operation_id=q.get('operation_id',[''])[0]))
                    elif path=='/api/logs':data=service.logs()
                    elif path=='/api/accounts':
                        q=parse_qs(urlsplit(self.path).query)
                        data=service.accounts(q.get('q',[''])[0],int(q.get('offset',['0'])[0]))
                    elif path=='/api/inventory':
                        from gm_console.accounts import inventory
                        q=parse_qs(urlsplit(self.path).query)
                        data=inventory(service.config,int(q.get('account',['0'])[0]),int(q.get('uid',['0'])[0]),int(q.get('offset',['0'])[0]),q.get('q',[''])[0])
                    elif path=='/api/categories':
                        from gm_console.catalog import facets
                        data=facets()
                    elif path=='/api/items':
                        from gm_console.catalog import search
                        q=parse_qs(urlsplit(self.path).query)
                        data=search(q.get('q',[''])[0],q.get('group',[''])[0],int(q.get('offset',['0'])[0]),q.get('icons',['0'])[0]=='1',q.get('category',[''])[0],q.get('sort',['relevance'])[0],q.get('ids',[''])[0])
                    else:return self.reply(404,dict(error='接口不存在'))
                    return self.reply(200,dict(ok=True,result=data))
                except Exception as e:return self.reply(400,dict(error=str(e) if isinstance(e,ValueError) else '读取失败'))
            target=STATIC/('index.html' if path=='/' else path.lstrip('/'))
            if not target.resolve().is_relative_to(STATIC.resolve()) or not target.is_file():return self.reply(404,dict(error='文件不存在'))
            kind={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml'}.get(target.suffix)
            if kind is None:return self.reply(404,dict(error='文件不存在'))
            self.reply(200,target.read_bytes(),kind)
        def do_POST(self):
            if not self.authorized():return self.reply(401,dict(error='管理认证失败'))
            if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):
                return self.reply(403,dict(error='请求来源无效'))
            if self.headers.get('Content-Type')!='application/json':return self.reply(415,dict(error='需要 JSON 请求'))
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=16384:raise ValueError('请求大小无效')
                self.connection.settimeout(10)
                value=json.loads(self.rfile.read(size))
                if not isinstance(value,dict):raise ValueError('请求需要是对象')
                action=urlsplit(self.path).path.removeprefix('/api/')
                if action not in ('start','stop','give','announce','rates','events','backup','cancel-announcement','set-level','coupon-issue','coupon-revoke','cash-credit'):return self.reply(404,dict(error='接口不存在'))
                return self.reply(200,dict(ok=True,result=service.mutate(action,value)))
            except Exception as e:return self.reply(400,dict(error=str(e) if isinstance(e,ValueError) else '操作失败，请检查日志'))
    return Handler


def serve_manager(service,server,stop_file):
    threading.Thread(target=server.serve_forever,daemon=True).start()
    requested_at=None;warned=False
    while True:
        try:
            if stop_file.exists() and not service.shutting_down:service.request_shutdown()
            if service.shutting_down:
                if requested_at is None:requested_at=time.monotonic()
                if service.shutdown_ready():break
                if not warned and time.monotonic()-requested_at>=90:
                    print('正常停服尚未完成，管理器及页面继续等待；未强制结束游戏。',flush=True);warned=True
            time.sleep(.5)
        except KeyboardInterrupt:service.request_shutdown()
        except Exception:
            service.message='管理器停止检查失败，继续保留监护；请核实日志及监听'
            print(service.message,flush=True);time.sleep(1)
    server.shutdown();server.server_close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--home',type=Path,required=True)
    p.add_argument('--port',type=int,default=18765);p.add_argument('--runtime-port',type=int,default=18766)
    p.add_argument('--autostart',action='store_true',help='启动时按上次保存的开关服状态恢复')
    p.add_argument('--stop-file',type=Path,help='仅允许部署根 run/gm.stop；正常停止管理器')
    p.add_argument('--forwarded-port',type=int,action='append',default=[],help='显式允许 SSH 本机入口的不同端口，仍只允许 loopback Host')
    a=p.parse_args()
    if not 1024<=a.port<=65535 or not 1024<=a.runtime_port<=65535 or a.port==a.runtime_port:p.error('端口无效')
    if any(not 1024<=port<=65535 for port in a.forwarded_port):p.error('转发入口端口无效')
    root=Path(__file__).resolve().parents[1]
    stop_file=(root/'run/gm.stop').resolve()
    if a.stop_file is not None and a.stop_file.resolve()!=stop_file:p.error('管理器停止文件必须是部署根 run/gm.stop')
    with SaveLease(a.home.resolve()/'supervisor'):
        service=Service(root,a.config,a.home,a.runtime_port)
        # Warm the catalog outside request threads; status remains responsive.
        def warm():
            from gm_console.catalog import catalog
            catalog()
        threading.Thread(target=warm,daemon=True).start()
        server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(service));server.daemon_threads=True
        server.gm_forwarded_ports={a.port,*a.forwarded_port}
        if a.autostart and not stop_file.exists():
            try:service.boot()
            except ValueError as e:service.message=str(e)
        print(f'GM: http://127.0.0.1:{a.port}/',flush=True)
        print(f'管理访问密钥保存在 {service.key_path}，不会写入日志或发布包。',flush=True)
        serve_manager(service,server,stop_file)
    return 0

if __name__=='__main__':raise SystemExit(main())
