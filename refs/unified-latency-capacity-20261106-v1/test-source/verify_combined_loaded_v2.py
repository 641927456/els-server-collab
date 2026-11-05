"""Verify concrete import origins for every proposed and retained source."""
import bootstrap,hashlib,importlib,json
H=bootstrap.HERE;P=H/'experiments/combined-latency-v2';manifest=json.loads((P/'manifest.json').read_bytes());loaded={}
for relative,digest in manifest['files'].items():
 path=P/'source'/relative;assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
 name=relative.removesuffix('.py').replace('/','.')
 module=importlib.import_module(name)
 assert module.__spec__.origin==str(path),(name,module.__spec__.origin,str(path))
 loaded[name]=dict(origin=module.__spec__.origin,sha256=digest)
assert len(loaded)==106
out=dict(passed=True,proposal_only=True,loaded_count=len(loaded),GIL_enabled=__import__('sys')._is_gil_enabled(),loaded=loaded)
assert not out['GIL_enabled']
(P/'loaded-origin-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps({k:v for k,v in out.items()if k!='loaded'}))
