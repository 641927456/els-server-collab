"""Loopback-only three-event GM panel; mutations use authenticated game worker RPC."""
import hmac,json,secrets,socket,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class Console:
    def __init__(self,port,runtime_port,token,home):
        if not (port==0 or 1024<=port<=65535) or not 1024<=runtime_port<=65535 or port==runtime_port or len(token)<40:
            raise ValueError('Distinct valid loopback GM ports and private runtime token required')
        self.runtime_port,self.token=runtime_port,token;home=Path(home);home.mkdir(parents=True,exist_ok=True)
        keypath=home/'selected2026-access.key'
        if not keypath.exists():
            with keypath.open('x',encoding='ascii') as stream:stream.write(secrets.token_urlsafe(48))
        self.key=keypath.read_text('ascii').strip()
        if len(self.key)<40:raise ValueError('GM UI key invalid')
        self.static=Path(__file__).resolve().parent/'data/selected2026/gm-static'
        console=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,value,kind='application/json; charset=utf-8'):
                raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.end_headers();self.wfile.write(raw)
            def host_ok(self):return self.headers.get('Host') in {f'{host}:{self.server.server_port}' for host in ('127.0.0.1','localhost')}
            def authorized(self):return self.host_ok() and hmac.compare_digest(self.headers.get('X-GM-Key','').encode(),console.key.encode())
            def do_GET(self):
                if not self.host_ok():return self.reply(403,dict(error='访问地址无效'))
                if self.path=='/api/selected2026':
                    if not self.authorized():return self.reply(401,dict(error='管理密钥无效'))
                    return self.call('selected2026-status')
                routes={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
                row=routes.get(self.path)
                if row is None:return self.reply(404,dict(error='页面不存在'))
                return self.reply(200,(console.static/row[0]).read_bytes(),row[1])
            def do_POST(self):
                if not self.authorized():return self.reply(401,dict(error='管理密钥无效'))
                if self.headers.get('Origin')!='http://'+self.headers.get('Host',''):return self.reply(403,dict(error='请求来源无效'))
                if self.path!='/api/selected2026':return self.reply(404,dict(error='接口不存在'))
                if self.headers.get('Content-Type')!='application/json':return self.reply(415,dict(error='需要JSON请求'))
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 1<=size<=16384:raise ValueError('请求大小无效')
                    self.connection.settimeout(10);value=json.loads(self.rfile.read(size))
                    if type(value) is not dict:raise ValueError('请求必须为对象')
                except (ValueError,TimeoutError):return self.reply(400,dict(error='活动设置请求格式无效'))
                return self.call('selected2026',value)
            def call(self,action,value=None):
                try:return self.reply(200,dict(ok=True,result=console.rpc(action,value)))
                except (OSError,TimeoutError):return self.reply(503,dict(error='活动服务尚未就绪或连接中断；请刷新状态，并保留原操作编号核对'))
                except ValueError as error:return self.reply(400,dict(error=str(error)))
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler);self.thread=None

    def rpc(self,action,value=None):
        with socket.create_connection(('127.0.0.1',self.runtime_port),timeout=5) as sock:
            sock.settimeout(20);sock.sendall((json.dumps(dict(token=self.token,action=action,value=value or {}))+'\n').encode())
            with sock.makefile('rb') as stream:raw=stream.readline(131073)
        if len(raw)>131072 or not raw.endswith(b'\n'):raise OSError('Unconfirmed runtime response')
        try:result=json.loads(raw)
        except ValueError:raise OSError('Unconfirmed runtime response') from None
        if not result.get('ok'):raise ValueError(result.get('error','管理操作失败'))
        return result['result']

    def start(self):
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def close(self):
        if self.thread is not None:self.server.shutdown();self.thread.join(timeout=5)
        self.server.server_close()
