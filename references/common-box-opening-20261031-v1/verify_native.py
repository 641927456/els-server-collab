from pathlib import Path
import hashlib,json,os,sys
H=Path(__file__).resolve().parent;R=Path(os.environ.get('ELS_COMMON_BOX_RUNTIME',H/'runtime'))
sys.path[:0]=[str(R),'G:/els/tools']
import els_server.domain.inventory_items
from verify_fixed_cubes_native import CubeReplay
r=CubeReplay();rows=[]
for path in sorted((H/'native-inputs').glob('*.json')):
 data=json.loads(path.read_text(encoding='utf8'));p=r.preview(bytes.fromhex(data['preview']));a=r.inventory(bytes.fromhex(data['inventory']));v=r.result(bytes.fromhex(data['result']))
 assert p['result']==0 and p['template']==data['template'] and v['result']==0 and a==v['items']
 rows.append(dict(template=data['template'],preview_entries=len(p['entries']),reward_entries=len(v['rewards']),inventory_entries=len(a),full_native_reader=True,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(rows)==15
out=dict(ok=True,live_process=False,natural_GUI=False,image_sha256='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229',rows=rows)
(H/'native-result.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(dict(ok=True,cases=len(rows))))
