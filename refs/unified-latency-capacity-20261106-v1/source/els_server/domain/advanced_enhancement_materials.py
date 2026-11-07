"""Current native restoration/fluorite templates, each codec verified."""
import functools,hashlib,json
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/advanced_enhancement_materials.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='04333df175b4ae8e71708c332f10f3e15fc160dfd2ee5707f2849bb6922ee098':raise ValueError('Advanced enhancement material catalog changed')
 c=json.loads(raw);proof=(PROJECT_ROOT/c['native_proof']).read_bytes();p=json.loads(proof)
 if c['client_sha256']!=CLIENT_SHA or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256'] or hashlib.sha256(proof).hexdigest()!=c['native_proof_sha256'] or not p['all_passed'] or p['live_process_access'] is not False or len(p['rows'])!=56:raise ValueError('Advanced enhancement material provenance')
 for row in c['items']:
  d=client_data().item(row['template'])
  if hashlib.sha256(d['record']).hexdigest()!=row['record_sha256'] or (d['item_type'],d['metadata'],row['group'])!=(7,row['metadata'],4):raise ValueError('Advanced material classification')
 return c

def restoration_templates():return tuple(catalog()['restoration_templates'])
