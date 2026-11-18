from pathlib import Path
import hashlib,json,sys
W=Path(__file__).resolve().parent;B=W.parent/'duel-wire-v2/full-source'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),'G:/els/tools/pylibs','G:/els']
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.character_rules import CLASSES
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
c=client_data();original=json.loads((W/'accessory-records.json').read_bytes());by_unit={};readers=[]
for r in original:
    t=r['template'];item=c.item(t);raw=item['record'];assert raw.hex()==r['record_hex']
    assert(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])==(0,2,1)
    assert item['equip_position']in(17,20,21,27)
    by_unit.setdefault(raw[210],[]).append(dict(template=t,quantity=1,inventory_days=7))
    readers.append(dict(template=t,name=item['name'],metadata=0,group=2,max_stack=1,
        record_sha256=hashlib.sha256(raw).hexdigest(),previously_registered=True,
        unit_type=raw[210],required_class=raw[211],equip_position=item['equip_position']))
assert set(by_unit)==set(range(1,16))
assert all(len(v)==(8 if k==10 else 4)for k,v in by_unit.items())
random_path=Path('G:/els/analysis/client-6c6b5180/20261014-062215/ice-resources/RandomItem.all-tables.json')
calls=json.loads(random_path.read_bytes())['__symbolic_calls__']
rule=next(c['arguments'][1]for c in calls if c['function']=='g_pRandomItemManager.AddRandomItemTemplet'and c['arguments'][1].get('m_ItemID')==166572)
item=c.item(166572)
with c.connect()as db:families=dict(db.execute('SELECT class_id,unit_type FROM units'))
data=dict(client_sha256=CLIENT_SHA,catalog_sha256=c.manifest['catalog_sha256'],
    box=dict(template=166572,name=item['name'],metadata=2,group=4,max_stack=999,
        record_sha256=hashlib.sha256(item['record']).hexdigest(),selection_count=0,
        class_outputs={str(k):by_unit[families[k]]for k in CLASSES},original_random_rule=rule),
    readers=readers,description_source_sha256=hashlib.sha256((W/'reward-descriptions.json').read_bytes()).hexdigest(),
    native_random_source_sha256=hashlib.sha256(random_path.read_bytes()).hexdigest(),
    derivation='Four named accessories from original item description; exact native item family/class bytes210/211; Lu/Ciel original main+minor groups give both four-piece sets; each inventory period7days')
p=W/'candidate/els_server/data/mentor_duelist_box.json';p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
print(hashlib.sha256(p.read_bytes()).hexdigest())
