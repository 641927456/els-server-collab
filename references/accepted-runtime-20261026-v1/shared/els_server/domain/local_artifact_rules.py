"""Versioned user-authorized local rules; never represented as retail formulas."""
import functools,hashlib,json,secrets
from pathlib import Path
from decimal import Decimal

def integer(value,low,high,label):
 if type(value) is not int or not low<=value<=high:raise ValueError(label)
 return value

@functools.lru_cache(maxsize=1)
def policy():
 raw=(Path(__file__).resolve().parents[1]/'data/local_artifact_rules.json').read_bytes();p=json.loads(raw)
 if p['schema_version']!=1 or p['provenance']!='local_design' or not isinstance(p['version'],str) or not p['version']:raise ValueError('Local policy provenance/version')
 rating=p['rating'];thresholds=rating['thresholds']
 if len(thresholds)!=8 or [r[1] for r in thresholds]!=list(range(8,0,-1)) or thresholds[-1][0]!=0:raise ValueError('Local rank coverage')
 if any(type(r[0]) is not int or not 0<=r[0]<=100 for r in thresholds) or any(a[0]<=b[0] for a,b in zip(thresholds,thresholds[1:])):raise ValueError('Rank thresholds')
 for key in ('minimum_budget_seconds','maximum_budget_seconds','seconds_per_stage','seconds_per_hostile','seconds_per_boss'):integer(rating[key],1,7200,key)
 if rating['minimum_budget_seconds']>rating['maximum_budget_seconds']:raise ValueError('Rating budget range')
 for value in rating['dungeon_budget_overrides'].values():integer(value,1,7200,'Dungeon rating budget')
 g=p['generation']
 if g['colors']!=[1,2,3,4,5]:raise ValueError('Original color identities')
 for key,n in (('color_weights',5),('family_weights',5),('value_weights',10)):
  if len(g[key])!=n:raise ValueError('Generation weight shape')
  for v in g[key]:integer(v,1,1000000,'Generation weight')
 if sum(g['value_weights'])!=10000:raise ValueError('Generation probabilities must total 100%')
 integer(g['preview_ed'],0,2**31-1,'Preview fee');integer(g['preview_fragments'],1,999,'Fragment quantity')
 e=p['experience']
 if e['eligibility']!='local_master_level_99' or e['ordinary_experience_bonuses']!='excluded':raise ValueError('Explicit local EXP eligibility required')
 integer(e['appropriate_clear_base'],1,2**31-1,'Artifact clear EXP')
 for k in ('maximum_medal_bp','maximum_event_bp','event_bp'):integer(e[k],0,100000,k)
 integer(e['kill_share_bp'],0,10000,'Kill EXP allocation');integer(e['synergy_bp'],0,10000,'Synergy bonus')
 if e['event_bp']>e['maximum_event_bp']:raise ValueError('Event EXP bound')
 return p

def identity():
 p=Path(__file__).resolve().parents[1]/'data/local_artifact_rules.json'
 return dict(version=policy()['version'],sha256=hashlib.sha256(p.read_bytes()).hexdigest(),provenance='local_design')

@functools.lru_cache(maxsize=1)
def generation():
 c=json.loads((Path(__file__).resolve().parents[1]/'data/artifact_generation.json').read_text(encoding='utf8'))
 from els_server.paths import PROJECT_ROOT
 from els_server.game_data import client_data
 if c['catalog_sha256']!=client_data().manifest['catalog_sha256'] or c['color_enum']!=client_data().resource('Enum.lua')['ARTIFACT_SPIRIT_SOCKET_COLOR_TYPE']:raise ValueError('Native generation build/color identity')
 for r in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/r['path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Native generation evidence changed')
 if set(c['pools'])!={'501','502','503','504'} or any(len(v)!=250 for v in c['pools'].values()):raise ValueError('Native spirit pools')
 return c

def weighted(values,weights,randbelow=secrets.randbelow):
 if len(values)!=len(weights) or not values or any(type(w) is not int or w<=0 for w in weights):raise ValueError('Random distribution')
 total=sum(weights);ticket=randbelow(total);integer(ticket,0,total-1,'Random entropy range')
 for value,weight in zip(values,weights):
  if ticket<weight:return value
  ticket-=weight
 raise ValueError('Unreachable distribution')

def spirit_type(template):
 from els_server.domain.artifact_progression import catalog
 if str(template) in generation()['generated']:return generation()['generated'][str(template)]['type']
 if template not in catalog()['equipment']:raise ValueError('Artifact equipment required')
 return {168600:502,168601:503,168602:504,168603:501,168915:502,168916:503,168917:504,168918:501}[template]

def spirit_group(template):return {501:18,502:19,503:20,504:21}[spirit_type(template)]

def validate_spirit(template,values):
 if not isinstance(values,(list,tuple)) or len(values)>1 or any(type(v) is not int for v in values):raise ValueError('Spirit option vector')
 allowed={r['ID'] for r in generation()['pools'][str(spirit_type(template))]}
 if any(v not in allowed for v in values):raise ValueError('Spirit effect belongs to another part')
 generated=generation()['generated'].get(str(template))
 if generated and any(next(r for r in generation()['pools'][str(generated['type'])] if r['ID']==v)['m_eArtifactSpiritSocketColorType']!=generated['color'] for v in values):raise ValueError('Generated stone color mismatch')
 return list(values)

def draw_spirit(template,material=None,randbelow=secrets.randbelow):
 typ=spirit_type(template);rule=policy()['generation'];c=generation();definition=None
 if material is not None:
  definition=c['materials'].get(str(material))
  if not definition or definition['type']!=typ:raise ValueError('Original shard does not match equipment part')
 family=definition['family'] if definition else weighted(range(5),rule['family_weights'],randbelow)
 color=definition['color'] if definition and definition['color'] else weighted(rule['colors'],rule['color_weights'],randbelow)
 level=9 if definition and definition['maximum'] else weighted(range(10),rule['value_weights'],randbelow)
 base=700000+(typ-501)*250
 rows=[r for r in c['pools'][str(typ)] if (r['ID']-base)//50==family and r['m_eArtifactSpiritSocketColorType']==color]
 rows.sort(key=lambda r:r['ID'])
 if len(rows)!=10:raise ValueError('Incomplete native family/color pool')
 return rows[level]['ID']

def generated_spirit(template,randbelow=secrets.randbelow):
 c=generation();d=c['generated'].get(str(template))
 if not d:raise ValueError('Generated native spirit template required')
 rule=policy()['generation'];family=weighted(range(5),rule['family_weights'],randbelow);level=weighted(range(10),rule['value_weights'],randbelow)
 base=700000+(d['type']-501)*250
 rows=sorted((r for r in c['pools'][str(d['type'])] if (r['ID']-base)//50==family and r['m_eArtifactSpiritSocketColorType']==d['color']),key=lambda r:r['ID'])
 if len(rows)!=10:raise ValueError('Generated native stone pool')
 return rows[level]['ID']

def draw_fixed(template,randbelow=secrets.randbelow):
 families=generation()['mirror_families'].get(str(template))
 if not families:raise ValueError('Mirror equipment required')
 values=weighted(families,[1]*len(families),randbelow)
 return weighted(values,list(range(len(values),0,-1)),randbelow)

def rating(dungeon,elapsed,stages,hostiles,bosses):
 for value,low,high,label in ((dungeon,1,2**31-1,'Dungeon'),(elapsed,0,2**31-1,'Active time'),(stages,1,1000,'Stage count'),(hostiles,0,100000,'Hostiles'),(bosses,0,10000,'Bosses')):integer(value,low,high,label)
 r=policy()['rating'];budget=r['dungeon_budget_overrides'].get(str(dungeon))
 if budget is None:budget=max(r['minimum_budget_seconds'],min(r['maximum_budget_seconds'],r['seconds_per_stage']*stages+r['seconds_per_hostile']*hostiles+r['seconds_per_boss']*bosses))
 score=min(100,100*budget//max(1,elapsed));rank=next(rank for minimum,rank in r['thresholds'] if score>=minimum)
 return dict(dungeon=dungeon,seconds=elapsed,stages=stages,hostiles=hostiles,bosses=bosses,budget=budget,score=score,rank=rank,policy=identity())

def assess_run(run,elapsed):
 stages=list(getattr(run,'stage_wires',{})) or [run.stage];hostiles=bosses=0
 for stage in stages:
  for part in run.graph['stages'][str(stage)]['parts'].values():
   groups=part['groups'];rows=list(groups[0]['npcs'])
   if len(groups)>1:rows+=max((g['npcs'] for g in groups[1:]),key=len)
   for r in rows:
    if r.get('active') and not r.get('ally') and r.get('team',1)!=0:
     hostiles+=1;bosses+=int(bool(r.get('boss')))
 return rating(run.identity,elapsed,len(stages),hostiles,bosses)

def clear_base(dungeon):
 """Local fixed award only for native appropriate-level content at level 99."""
 integer(dungeon,1,2**31-1,'Artifact clear dungeon')
 from els_server.game_data import client_data
 from els_server.domain.seal_quests import appropriate_level_range
 low,high=appropriate_level_range(client_data().dungeon(dungeon))
 return policy()['experience']['appropriate_clear_base'] if low<=99<=high else 0

def experience(character,clear_base,kill_base=0,*,medals=(),synergy=False,event_bp=None):
 for v in (clear_base,kill_base):integer(v,0,2**63-1,'Unboosted Artifact base EXP')
 if type(synergy) is not bool:raise ValueError('Synergy state')
 e=policy()['experience'];event=e['event_bp'] if event_bp is None else event_bp
 integer(event,0,e['maximum_event_bp'],'Artifact event bonus')
 medals=list(medals)
 for v in medals:integer(v,0,e['maximum_medal_bp'],'Artifact medal bonus')
 a=character.get('artifact');eligible=character.get('master') is True and character.get('level')==99 and isinstance(a,dict)
 if not eligible:return dict(clear=0,kill=0,total=0,eligible=False,policy=identity())
 from els_server.domain.artifact_progression import catalog,require_artifact
 require_artifact(character)
 potential=next((int(Decimal(str(r['native'].get('m_fMasterArtifactIncreaseExpRate',0)))*10000) for r in catalog()['potential_groups'][2] if r['option']==a['potentials'][2]),0)
 medal=max(medals,default=0);common=10000+potential+medal
 clear=clear_base*common*(10000+event)//100000000
 kill=kill_base*(common+(e['synergy_bp'] if synergy else 0))*(10000+event)//100000000
 if clear+kill>=2**63:raise ValueError('Artifact EXP overflow')
 # Native growth discards overflow at an evolution boundary. Record only
 # applied EXP, with clear EXP taking the remaining capacity before kill EXP.
 from els_server.game_data import client_data
 capacity=max(0,int(client_data().artifact_curve(a['evolution'])[-1]['TOTAL_ARTIFACT_EXP'])-a['experience']) if a['evolution']<4 else 0
 offered=clear+kill;clear=min(clear,capacity);kill=min(kill,capacity-clear)
 return dict(clear=clear,kill=kill,total=clear+kill,offered=offered,capped=offered>clear+kill,eligible=True,potential_bp=potential,medal_bp=medal,synergy_bp=e['synergy_bp'] if synergy else 0,event_bp=event,policy=identity())
