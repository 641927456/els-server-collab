"""Pin original fourteen mentor tasks and the two explicit current CN rewards."""
from pathlib import Path
import copy,hashlib,json,struct,sys
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from extract_launcher_assets import index
ids={*range(45001,45005),*range(45031,45041)}
data=client_data()
qproof=json.loads((W/'quest-definition-candidates.json').read_bytes())
assert hashlib.sha256(Path(qproof['source_path']).read_bytes()).hexdigest()==qproof['source_sha256']
quests=copy.deepcopy(qproof['quests']);assert set(map(int,quests))==ids
native=json.loads((R/'analysis/seal-quests-20261015/FieldSubQuest.tables.json').read_bytes())
sub_ids={v for q in quests.values()for k,v in q['m_vecSubQuest'].items()if str(k)!='0'and v is not None}
subs={str(c['arguments'][1]['m_iID']):c['arguments'][1]for c in native['__symbolic_calls__']
      if c['function'].endswith('.AddSubQuestTemplet_LUA')and c['arguments'][1]['m_iID']in sub_ids}
assert set(map(int,subs))==sub_ids
quests['45002']['Reward']['m_vecItem']={'1':dict(m_iItemID=189800,m_iQuantity=1,m_iPeriod=7,m_sSocketOption=0)}
quests['45039']['Reward']['m_vecItem']={'1':dict(m_iItemID=132812,m_iQuantity=10,m_iPeriod=0,m_sSocketOption=0)}
reward_ids={v['m_iItemID']for q in quests.values()for k,v in q['Reward']['m_vecItem'].items()if str(k)!='0'and isinstance(v,dict)}
definitions=[]
for t in sorted(reward_ids|{189802,189803}):
    item=data.item(t);raw_stack=struct.unpack_from('<I',item['record'],16)[0]
    old=t in VERIFIED_TEMPLATES
    group=TEMPLATE_BAG_GROUPS[t]if old else 5 if item['item_type']==8 else 4
    definitions.append(dict(template=t,name=item['name'],metadata=item['metadata'],group=group,
        max_stack=TEMPLATE_MAX_STACKS[t]if old else max(1,raw_stack),item_type=item['item_type'],
        raw_max_stack=raw_stack,record_sha256=hashlib.sha256(item['record']).hexdigest(),previously_registered=old))
archive=Path('D:/艾尔之光/data/data036.kom')
directory={r['Name']:r for r in index(archive,(R/'analysis/x2-runtime.bin').read_bytes())}
old_proof=json.loads((R/'analysis/seal-quests-20261015/resource-native-proof.json').read_bytes())
source=[]
for name in('FieldQuest.lua','FieldSubQuest.lua'):
    old=next(r for r in old_proof['rows']if r['name']==name);current=directory[name]
    assert all(old['source'][k]==current[k]for k in('Size','CompressedSize','Checksum','MappedID','offset'))
    raw=R/'analysis/seal-quests-20261015'/name;assert hashlib.sha256(raw.read_bytes()).hexdigest()==old['sha256']
    source.append(dict(name=name,path=str(raw),sha256=old['sha256'],entry=current,
                       native_proof=str(R/'analysis/seal-quests-20261015/resource-native-proof.json')))
pool=json.loads((W/'stone-box-policy-authorization.json').read_bytes())
assert [r['template']for r in pool['entries']]==[132198,132202,132203,132204,132205]
out=dict(schema_version=1,policy='mentor-native-tasks-current-CN-20261106-v1',client_sha256=CLIENT_SHA,
    catalog_sha256=data.manifest['catalog_sha256'],quests=quests,subquests=subs,reward_definitions=definitions,
    teacher_repeat_ids=list(range(45001,45005)),native_repeat_type=2,
    original_source=source,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    overrides=[dict(quest=45002,reason='Current CN guide specifies189800x1/7days instead of the old potion vector'),
               dict(quest=45039,reason='Current CN guide specifies ten first-grade stone boxes; approved five-stone pool')],
    official_source='https://els.ztgame.com/game/m_004-1635-002fb-306817.shtml?ms=763',
    stone_box=dict(template=132812,native_group=14970,entries=pool['entries'],
        authorization_sha256=hashlib.sha256((W/'stone-box-policy-authorization.json').read_bytes()).hexdigest()),
    teacher_quest_level='Retain the exact native per-task70 condition; it does not alter the current second-job teacher relation eligibility')
dest=W/'candidate/els_server/data/mentor_quests.json';dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf8')
(W/'quest-data-build.json').write_text(json.dumps(dict(ok=True,path=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
    quests=len(quests),subquests=len(subs),definitions=len(definitions),unregistered=[r['template']for r in definitions if not r['previously_registered']],
    original_source_reused=True,gameplay_overrides=out['overrides']),indent=2)+'\n','utf8')
print(json.dumps(dict(quests=len(quests),subquests=len(subs),definitions=definitions,sha256=hashlib.sha256(dest.read_bytes()).hexdigest()),ensure_ascii=False))
