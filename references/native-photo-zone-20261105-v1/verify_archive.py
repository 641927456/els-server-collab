"""Verify the exact reviewed source/data and the sanitized acceptance record."""
from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((r/'candidate-manifest.json').read_bytes())
assert len(m['files'])==22
assert m['new_tables']==['native_photo_zone_unlocks']
for row in m['files']:
    p=(r/'source'/row['path']).resolve()
    assert p.is_relative_to(r/'source')and p.stat().st_size==row['bytes']and sha(p)==row['sha256']
    if p.suffix=='.py':ast.parse(p.read_bytes())
    elif p.suffix=='.json':json.loads(p.read_bytes())
v=json.loads((r/'verification.json').read_bytes())
assert v['ok']and v['source_manifest_sha256']==sha(r/'candidate-manifest.json')
assert not v['raw_runtime_traffic_included']and not v['natural_GUI']
assert v['SQL_distinct_cases']==8 and v['UDP_cases']==3 and v['native_DTO_cases']==12
assert len(v['TLS'])>=4
data=r/'source/els_server/data'
catalog=json.loads((data/'photo_zone.json').read_bytes())
assert len(catalog['maps'])==23
assert sum(not row.get('m_Lock')for row in catalog['maps'].values())==5
assert len(catalog['quests'])==len(catalog['subquests'])==8
assert set(map(int,catalog['tickets']))=={288494}
assert set(map(int,catalog['cameras']))=={288495}
print('22 reviewed source/data identities and sanitized related verification records passed')
