"""Reuse the already qualified native710160 tiers, with the newly approved exact weights."""
from pathlib import Path
import hashlib,json,math,sys
K=Path(__file__).resolve().parent;S=K/'reward-source-v1';R=Path('G:/els')
sys.dont_write_bytecode=True;sys.path.insert(0,str(S))
from els_server.game_data import client_data,CLIENT_SHA
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=S/'els_server/data/current_magic_stones.json';current=json.loads(source.read_bytes())
description=S/'analysis/sol-high-20261015/equipment-ui-v5/native-stone-descriptions.json'
desc=next(r for r in json.loads(description.read_bytes())['rows']if r['template']==109956)['description']
assert all(x in desc for x in ('+6~9%','+8~14%','+9~13.5%','+12~18%','һ����ֵ'))
approval=json.loads((K/'approved-server-rules-20261106-v2.json').read_bytes())['highest_magic_stone']
assert approval['template']==109956 and approval['category_count']==12
used={};profiles={};categories={}
for kind in('weapon','armor'):
    groups=next(r['categories']for r in current['summary']if r['template']==710160 and r['kind']==kind)
    assert len(groups)==12
    mass=math.lcm(*(len(r['tiers'])for r in groups));profile=[];categories[kind]=[]
    for group in groups:
        tiers=group['tiers'];weight=mass//len(tiers)
        categories[kind].append(dict(field=group['field'],low=group['low'],high=group['high'],options=[r['option']for r in tiers]))
        for tier in tiers:
            option=tier['option'];used[str(option)]=current['options'][str(option)]
            profile.append(dict(option=option,weight=weight))
    assert len({r['option']for r in profile})==len(profile)and sum(r['weight']for r in profile)==12*mass
    profiles['highest-'+kind]=profile
item=client_data().item(109956)
data=dict(policy='highest-magic-stone-equal-20261106-v1',human_choice=approval['question_id'],client_sha256=CLIENT_SHA,
          catalog_sha256=client_data().manifest['catalog_sha256'],items={'109956':dict(template=109956,name=item['name'],metadata=2,group=4,
          record_sha256=hashlib.sha256(item['record']).hexdigest(),profiles={k:'highest-'+k for k in('weapon','armor')})},
          profiles=profiles,options=used,categories=categories,
          sources=[dict(path=p.relative_to(S).as_posix(),sha256=sha(p))for p in(source,description)],
          numerical_policy='Exact uniform twelve categories; exact uniform native legal tiers within each category. Integer LCM mass, no rounding. Armor uses the existing native half-range tiers.')
dest=S/'els_server/data/highest_magic_stone.json';dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(data_sha256=sha(dest),profiles={k:dict(outcomes=len(v),total=sum(r['weight']for r in v))for k,v in profiles.items()})))
