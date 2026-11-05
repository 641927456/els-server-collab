"""Current native personal guild quests; progress comes from accepted producers."""
from functools import lru_cache
from pathlib import Path
import hashlib,json

@lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/guild_quests.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='7afdc43b50de08a7e430fc618e4e75c9bfd4450a12da5be437d124bc9fe03115':raise ValueError('Guild quest source changed')
 return json.loads(raw)

def contains(qid):return str(qid)in catalog()['quests']
def weekly(qid):return contains(qid)and bool(catalog()['quests'][str(qid)]['m_bRepeat'])

def objective(sub):return catalog()['subquests'].get(str(sub.get('m_iID')))==sub

def target(sub):
 if not objective(sub):raise ValueError('Unknown guild objective')
 kind=sub['m_eClearType'];c=sub['m_ClearCondition']
 return 1 if kind==1 else c['m_iPVPWin']if kind==10 else c.get('m_iClearCount',c.get('m_iDungeonClearCount'))

def definitions():
 from els_server.game_data import client_data
 from els_server.domain.activity_2026_stack_policy import effective_stack
 for row in catalog()['reward_definitions']:
  item=client_data().item(row['template'])
  if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or item['metadata']!=row['metadata']:raise ValueError('Guild quest reward differs from current source')
  yield dict(template=row['template'],metadata=row['metadata'],group=row['group'],max_stack=effective_stack(row['max_stack']))

def increment(sub,activities):
 if not objective(sub):return 0
 kind=sub['m_eClearType'];c=sub['m_ClearCondition'];total=0
 for typ,amount,template in activities:
  if typ!=kind:continue
  if kind==69 and template not in tuple(v for k,v in c['m_listUseItemID'].items()if k!='0'):continue
  total+=amount
 return total

def timed_selection(quest,reward):
 return catalog()['quests'].get(str(quest.get('m_iID')))==quest and reward in tuple(quest['SelectReward'].get('m_vecSelectItem',{}).values())and reward.get('m_iPeriod',0)>0

def timed_plan(quest,reward,now):
 if not timed_selection(quest,reward):raise ValueError('Timed reward outside current guild source')
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
 from els_server.domain.item_expiration import validate
 t=reward['m_iItemID']
 return dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=reward['m_iQuantity'],expires_at=validate(now+reward['m_iPeriod']*86400))
