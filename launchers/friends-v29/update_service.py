"""Read-only signed launcher files and content-addressed runtime components."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json,re,ssl,threading,zipfile
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'public'
SLOTS=threading.BoundedSemaphore(2)

class Server(ThreadingHTTPServer):
 daemon_threads=True
 def get_request(self):
  raw,address=super().get_request();raw.settimeout(12)
  try:return self.tls.wrap_socket(raw,server_side=True),address
  except Exception:raw.close();raise

class Handler(BaseHTTPRequestHandler):
 server_version='ELS-Launcher-Update';sys_version=''
 def log_message(self,*args):pass
 def do_GET(self):self.respond(False)
 def do_HEAD(self):self.respond(True)
 def artifact_headers(self,name,size,json_type=False):
  self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8' if json_type else 'application/octet-stream')
  self.send_header('Content-Length',str(size));self.send_header('Cache-Control','no-store' if json_type else 'public, max-age=31536000, immutable')
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Disposition','inline' if json_type else 'attachment; filename="'+name+'"');self.end_headers()
 def respond(self,head):
  if not SLOTS.acquire(blocking=False):self.send_error(503);return
  try:
   url=urlsplit(self.path)
   if url.query or url.fragment or not url.path.startswith('/launcher-updates/'):
    self.send_error(404);return
   name=url.path.removeprefix('/launcher-updates/')
   if re.fullmatch(r'blob-[a-f0-9]{64}\.bin',name):
    # This index is publisher-owned, never provided by a request. The service
    # reads an existing immutable ZIP; it does not write/extract/run anything.
    index=json.loads((ROOT/'components-index.json').read_text('utf8'));row=index.get(name[5:-4])
    if row is None:self.send_error(404);return
    archive=row['archive'];entry=row['entry'];size=row['size']
    if not re.fullmatch(r'runtime-[a-f0-9]{64}\.zip',archive) or not isinstance(size,int) or not 0<=size<=268435456:
     self.send_error(503);return
    allowed=json.loads((ROOT/'allowlist.json').read_text('utf8'));path=PUBLIC/archive
    if archive not in allowed or not path.is_file() or path.is_symlink():self.send_error(404);return
    with zipfile.ZipFile(path) as z:
     info=z.getinfo(entry)
     if info.is_dir() or info.file_size!=size:self.send_error(503);return
     self.artifact_headers(name,size)
     if not head:
      with z.open(info) as source:
       while chunk:=source.read(65536):self.wfile.write(chunk)
    return
   if name!='latest.json' and not re.fullmatch(r'(v[0-9]{2,8}-[a-f0-9]{16}\.exe|runtime-[a-f0-9]{64}\.zip)',name):
    self.send_error(404);return
   path=PUBLIC/name
   if not path.is_file() or path.is_symlink():self.send_error(404);return
   allowed=json.loads((ROOT/'allowlist.json').read_text('utf8'))
   if name not in allowed:self.send_error(404);return
   with path.open('rb') as source:
    self.artifact_headers(name,path.stat().st_size,name=='latest.json')
    if not head:
     while chunk:=source.read(65536):self.wfile.write(chunk)
  except (ConnectionError,TimeoutError,OSError):pass
  except (ValueError,KeyError,zipfile.BadZipFile):
   self.close_connection=True
  finally:SLOTS.release()

if __name__=='__main__':
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
 context.load_cert_chain(ROOT/'tls/service.crt',ROOT/'tls/service.key')
 server=Server(('0.0.0.0',19411),Handler);server.tls=context;server.serve_forever()
