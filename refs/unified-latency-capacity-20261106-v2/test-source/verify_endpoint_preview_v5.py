"""Run the compiled endpoint against an installed own workspace and private ports."""
from pathlib import Path
import importlib.util,json,os,socket,subprocess,tempfile
H=Path(__file__).resolve().parent;
import sys
sys.path.insert(0,'G:/els/tools/pylibs')
import psutil
owner=psutil.Process();owner.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS);owner.ionice(psutil.IOPRIO_LOW)
assert int(owner.nice())==16384 and int(owner.ionice())==1
D=H/'launcher-preview-v5';binding=json.loads((D/'built-selection-verification.json').read_bytes());root=Path(binding['selected_root'])
build=json.loads((D/'build.json').read_bytes());source=H/'verify_endpoint_scheduling.cs';exe=source.with_suffix('.exe')
compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
q=subprocess.run([str(compiler),'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll',str(source)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=60)
assert q.returncode==0,q.stdout.decode('utf8','replace')
spec=importlib.util.spec_from_file_location('endpoint_owned_runner',Path('G:/els/analysis/scroll-mhp-delivery-20261101-v1/launcher_components_owned_process.py'));owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned);owned.RECEIPTS=D/'endpoint-owned-processes'
def port():
 with socket.socket()as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='owned-compiled-endpoint-',dir=H)as raw:
 workspace=Path(raw);result=workspace/'installed.json'
 q=owned.run([root/'python/python.exe','-B',root/'tools/install_unified_runtime.py','--workspace',workspace,'--manifest',D/'runtime-files.json','--result',result],timeout=120)
 assert json.loads(result.read_bytes())['ok']
 config=workspace/'state/unified-server/server.toml'
 import tomllib
 values=tomllib.loads(config.read_text('utf8'))['server'];values.update(port=port(),client_probe_port=port())
 config.write_text('[server]\n'+''.join(k+' = '+(str(v).lower()if type(v)is bool else json.dumps(v))+'\n'for k,v in values.items()),'utf8')
 result=workspace/'endpoint-result.json';q=owned.run([exe,build['exe'],workspace,result],timeout=120)
 out=json.loads(result.read_bytes());assert out['passed']and out['normal_stop']
 out.pop('child_pid');out.pop('actual_server_interpreter');out['selected_payload_sha256']=binding['payload_sha256']
 events=[]
 for path in workspace.rglob('server.jsonl'):
  for line in path.read_text('utf8').splitlines():
   event=json.loads(line)
   if event.get('event')=='server_scheduling':events.append(event)
 assert events and all(event['priority_class']==32 and event['IO_priority']==2 for event in events)
 out.update(actual_game_IO_priority=2,actual_startup_scheduling_readback=True,original_parent_CPU_priority=16384,original_parent_IO_priority=1)
out['owned_workspace_removed']=not workspace.exists()
(H/'endpoint-preview-v5-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
