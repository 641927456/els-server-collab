"""Pinned Master Artifact curves, potential pools and equipment identities."""
import functools,hashlib,json,secrets
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
 p=Path(__file__).resolve().parents[1]/'data/artifact_progression.json';raw=p.read_bytes()
 manifest=json.loads(p.with_suffix('.manifest.json').read_text());c=json.loads(raw)
 if hashlib.sha256(raw).hexdigest()!=manifest['sha256'] or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Artifact catalog identity')
 for r in c['definitions']:
  if hashlib.sha256(client_data().item(r['template'])['record']).hexdigest()!=r['record_sha256'] or r['native']!={'ok':1,'consumed':304}:raise ValueError('Artifact native item identity')
 if [sum(r['weight'] for r in g) for g in c['potential_groups']]!=[100000]*3:raise ValueError('Artifact probability totals')
 return c

def slots(template):
 if template not in catalog()['equipment']:return ()
 position=client_data().item(template)['equip_position']
 return (3,4) if position==46 else (position-43,) if position in (43,44,45) else ()

def skill_choices(character):
 from els_server.domain.equipment_requirements import catalog as requirements
 route=requirements()[0][character['unit_class']]['route']
 return catalog()['skill_choices'][str(character['unit_type'])].get(str(route),[])

def require_artifact(character):
 from els_server.domain.character_rules import artifact_wire
 artifact_wire(character)
 if not character.get('master') or not character.get('artifact'):raise ValueError('Artifact is not unlocked')
 a=character['artifact'];choices=a['potentials'];stage=a['evolution']
 if any(v and v not in {r['option'] for r in catalog()['potential_groups'][n]} for n,v in enumerate(choices[:3])):raise ValueError('Invalid native potential group')
 if stage<3 and any(choices) or stage<5 and choices[3]:raise ValueError('Potential stage is not unlocked')
 # A route change may retain an old choice for display, but cannot select it anew.
 all_skills={v for ids in catalog()['skill_choices'][str(character['unit_type'])].values() for v in ids}
 if choices[3] and choices[3] not in all_skills:raise ValueError('Unknown dual-trait potential')
 curve=client_data().artifact_curve(stage)
 if not 0<=a['experience']<=int(curve[-1].get('TOTAL_ARTIFACT_EXP',0)):raise ValueError('Artifact experience exceeds native stage cap')
 expected=max(r['ARTIFACT_LEVEL'] for r in curve if r.get('TOTAL_ARTIFACT_EXP',0)<=a['experience'])
 if a['level']!=expected:raise ValueError('Artifact level and experience disagree')
 return dict(a,potentials=list(choices))

def grow(character,experience):
 if type(experience) is not int or not 0<=experience<2**63:raise ValueError('Artifact experience amount')
 a=require_artifact(character);stage=a['evolution']
 if stage>=4 or not experience:return a
 curve=client_data().artifact_curve(stage);maximum=int(curve[-1]['TOTAL_ARTIFACT_EXP'])
 total=min(maximum,a['experience']+experience)
 if total>=maximum:
  # Native receiver clamps at this stage's cap; overflow is not carried onward.
  return dict(a,evolution=stage+1,level=1,experience=0)
 return dict(a,level=max(r['ARTIFACT_LEVEL'] for r in curve if r['TOTAL_ARTIFACT_EXP']<=total),experience=total)

def draw(index,randbelow=secrets.randbelow):
 if type(index) is not int or index not in range(3):raise ValueError('Random potential slot')
 ticket=randbelow(100000)
 if type(ticket) is not int or not 0<=ticket<100000:raise ValueError('Potential entropy bound')
 for row in catalog()['potential_groups'][index]:
  if ticket<row['weight']:return row['option']
  ticket-=row['weight']
 raise ValueError('Incomplete potential distribution')

def use_consumable(character,template,count):
 a=require_artifact(character)
 # 22236C0 caps both item dialogs at global level ordinal 19 = stage 3, level 1.
 if type(count) is not int or not 1<=count<=99 or a['evolution']>=3:raise ValueError('Artifact item growth stage/count')
 ordinal=(a['evolution']-1)*9+a['level']
 if count>19-ordinal:raise ValueError('Artifact bulk count exceeds native dialog cap')
 is_scroll=template in catalog()['level_up_items'];amount=catalog()['exp_potions'].get(str(template))
 if not is_scroll and amount is None:raise ValueError('Unknown Artifact growth item')
 for _ in range(count):
  if a['evolution']>=3:raise ValueError('Artifact bulk item request crosses its permitted stages')
  if is_scroll:
   curve=client_data().artifact_curve(a['evolution'])
   current=next(row for row in curve if row['ARTIFACT_LEVEL']==a['level'])
   target=next(row for row in curve if row['ARTIFACT_LEVEL']==a['level']+1)
   # Authorized local policy preserves the filled fraction, not a fixed raw
   # EXP amount. Stage caps retain the existing native transition behavior.
   from els_server.domain.local_artifact_rules import policy
   if policy()['experience']['scroll_partial_progress']!='preserve_fraction':raise ValueError('Unsupported scroll carry policy')
   low=int(current['TOTAL_ARTIFACT_EXP']);high=int(target['TOTAL_ARTIFACT_EXP'])
   following=next((r for r in curve if r['ARTIFACT_LEVEL']==a['level']+2),None)
   carried=(a['experience']-low)*(int(following['TOTAL_ARTIFACT_EXP'])-high)//(high-low) if following else 0
   a=grow(dict(character,artifact=a),high+carried-a['experience'])
  else:a=grow(dict(character,artifact=a),amount)
 return a

def potential(character,index,reset,chosen,randbelow=secrets.randbelow):
 a=require_artifact(character)
 if type(index) is not int or index not in range(4) or type(reset) is not bool or type(chosen) is not int:raise ValueError('Artifact potential request')
 if a['evolution']<(5 if index==3 else 3):raise ValueError('Potential slot is sealed')
 if bool(a['potentials'][index])!=reset:raise ValueError('Potential identification/reset state')
 if reset:
  if chosen:raise ValueError('Reset cannot select a new skill')
  value=0
 elif index==3:
  if chosen not in skill_choices(character):raise ValueError('Skill does not belong to current role and route')
  value=chosen
 else:
  if chosen:raise ValueError('Random potential cannot be chosen by the client')
  value=draw(index,randbelow)
 a['potentials'][index]=value
 return a

def require_wearable(item,character):
 require_artifact(character)
 from els_server.domain.item_expiration import require_current
 from els_server.domain.equipment_requirements import class_matches
 require_current(item);raw=client_data().item(item['template'])['record']
 if item.get('identified') is False:raise ValueError('Artifact equipment must be identified before wearing')
 if item['slot'] not in slots(item['template']) or item['count']!=1:raise ValueError('Artifact equipment slot')
 if character['level']<raw[0xd1] or raw[0xd2] and raw[0xd2]!=character['unit_type'] or not class_matches(character['unit_class'],raw[0xd3]):raise ValueError('Artifact equipment character requirement')
