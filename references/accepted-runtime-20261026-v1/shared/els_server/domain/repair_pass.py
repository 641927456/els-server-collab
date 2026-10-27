"""Native category-126 pass; delivery activation rules remain source-specific."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA,DATA_DIR

TEMPLATE=711611

@functools.lru_cache(maxsize=1)
def definition():
    d=json.loads((DATA_DIR/'repair_pass.json').read_text(encoding='utf8'))
    item=client_data().item(TEMPLATE)
    if (d['schema_version']!=1 or d['client_sha256']!=CLIENT_SHA or d['template']!=TEMPLATE
        or (d['metadata'],d['group'],d['max_stack'])!=(0,4,1)
        or d['requires_explicit_deadline'] is not True
        or item['metadata']!=0 or item['item_type']!=7
        or hashlib.sha256(item['record']).hexdigest()!=d['source_record_sha256']):raise ValueError('Repair pass identity')
    root=Path(__file__).resolve().parents[2]
    raw=(root/d['native_evidence']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=d['native_evidence_sha256']:raise ValueError('Repair pass proof changed')
    rows=[r for r in json.loads(raw)['proof']['rows'] if r['template']==TEMPLATE]
    if rows!=d['cases'] or len(rows)!=4 or [r['expired'] for r in rows]!=[0,1,0,0]:raise ValueError('Repair pass proof scope')
    if any(r['consumed']!=r['size'] or r['metadata']!=0 or r['group']!=4 or r['lock_until']!='0' for r in rows):raise ValueError('Repair pass native body')
    return d
