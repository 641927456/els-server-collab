"""All native career routes, distinct product stages and no free/event copies."""
import collections,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.storage.shop_state import catalog
BASE=ROOT/'analysis/client-6c6b5180'
data=json.loads((BASE/'native-job-shop-catalog.json').read_text(encoding='utf8'))
for source in data['sources']:
    assert hashlib.sha256((BASE/source['path']).read_bytes()).hexdigest()==source['sha256']
rows=data['rows'];assert len(rows)==541
assert collections.Counter(r['job_kind'] for r in rows)=={'advancement_1':60,'advancement_2':60,'advancement_3':60,'class_change':180,'transcendence_change':60,'master_change':60,'master_advancement':60,'transcendence_book':1}
assert len({(r['name'],bytes.fromhex(r['record_hex'])[210:212]) for r in rows})==len(rows)
assert not any(re.search('科宝|阿莉尔|路莉尔|测试|艾因1-[12]次',r['name']) for r in rows)
for stage in ('advancement_1','advancement_3','master_advancement','master_change'):
    assert collections.Counter(bytes.fromhex(r['record_hex'])[210] for r in rows if r['job_kind']==stage)==dict.fromkeys(range(1,16),4)
# The explicit native master-class condition table covers every selected route.
resource=json.loads((BASE/'20261014-215604/job-resources/TranscendentalClassItem.tables.json').read_text(encoding='utf8'))
classes=json.loads((BASE/'resource-scripts/CashShopCategory.resolved.json').read_text(encoding='utf8'))['UNIT_CLASS']
native={c['arguments'][1]:classes[c['arguments'][2]['global'].split('.')[-1]] for c in resource['__symbolic_calls__'] if c['function'].endswith('.AddMasterClassItem') and isinstance(c['arguments'][2],dict)}
masters=[r for r in rows if r['job_kind']=='master_advancement']
assert len({native[r['id']] for r in masters})==60
assert all(bytes.fromhex(r['record_hex'])[211]==native[r['id']] for r in masters)
offers={r['template']:r for r in catalog()}
assert all(r['id'] in offers and offers[r['id']]['category']==32 for r in rows)
assert {214410,214420,242310,318852,297617,298070,298452,318854} <= set(offers)
print('PASS: 541 distinct native career products; 15 characters and 60 routes, all stages, native master conditions, no event/free duplicates.')
