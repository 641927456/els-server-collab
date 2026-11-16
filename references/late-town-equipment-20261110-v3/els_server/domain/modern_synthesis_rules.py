"""Atma synthesis for the original stone and accessory-breath recipe families.

Current Lua gives ED/upgrade rates. The four ordinary stone result families
are drawn uniformly by this compatibility-v1 policy; no retail family-weight
claim. Accessory weights come from Nexon's published exact outcome tables.
"""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data
POLICY='atma-ordinary-stone-synthesis-compat-v1'

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/modern_synthesis.json').read_bytes();c=json.loads(raw)
 if hashlib.sha256(raw).hexdigest()!='4173632dcb396247592e76759afedef5daf692b93e37fa62bafb90e71fc0ccad':raise ValueError('Synthesis rules changed')
 if c['policy']!=POLICY or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Synthesis source identity')
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
 for key,row in c['items'].items():
  t=int(key);d=client_data().item(t)
  if hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']or(d['item_type'],d['metadata'])!=(7,2)or VERIFIED_TEMPLATES.get(t)!=2 or TEMPLATE_BAG_GROUPS.get(t)!=4:raise ValueError('Synthesis current ordinary stone')
 return c

def input_key(item):
 from els_server.domain.atma_accessories import input_grade
 template=item['template']
 row=catalog()['items'].get(str(template))
 if row is not None and item['group']==4:return 'stone',row['grade']
 grade=input_grade(template)
 if grade is not None and item['group']==3:return 'accessory',grade
 raise ValueError('Unqualified synthesis input')


def recipe_for(key):
 family,grade=key
 if family=='stone':return catalog()['recipes'][str(grade)]
 from els_server.domain.atma_accessories import catalog as accessories
 return accessories()['recipes'][str(grade)]


def output_ids(recipe):
 if 'weights'in recipe:return {template for template,weight in recipe['weights']}
 return set(recipe['same_pool']+recipe['upgraded_pool'])


def quote(selected):
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 keys=set()
 for item,amount in selected:
  require_current(item);require_unlocked(item)
  if amount>item['count']or item.get('sealed')or item.get('identified')is False:raise ValueError('Unqualified synthesis input')
  keys.add(input_key(item))
 if len(keys)!=1:raise ValueError('Synthesis same type and quality required')
 recipe=recipe_for(keys.pop());total=sum(n for _,n in selected)
 return recipe,total//3

def draw(recipe,randbelow):
 if 'weights'in recipe:
  ticket=randbelow(10_000_000)
  if type(ticket)is not int or not 0<=ticket<10_000_000:raise ValueError('Atma synthesis random ticket')
  for template,weight in recipe['weights']:
   if ticket<weight:return template
   ticket-=weight
  raise ValueError('Atma synthesis probability total')
 # Each result is real, including failure to improve the input quality.
 improved=randbelow(100)<recipe['upgrade_percent']
 pool=recipe['upgraded_pool']if improved else recipe['same_pool']
 return pool[randbelow(len(pool))]


def require_npc(db,owner,account_id):
 # Current menu59 exists only at House40274/NPC10384/Magmelia world1023.
 # Its native click is local UI0x78; no fictional FD/dialogue-token prerequisite.
 npc=catalog()['npc']
 from els_server.storage.local_state import TOWN_SCENES
 if TOWN_SCENES.get(npc['town'])!=npc['world']or db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(npc['town'],):raise ValueError('Current synthesis NPC town')
 from els_server.storage.seal_quests import load_character,completed_ids
 from els_server.domain.town_travel import require_destination
 character=load_character(db,owner,account_id)
 records={r[0]for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(owner,))}if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='dungeon_records'").fetchone()else set()
 row=require_destination(npc['town'],character,completed_ids(db,owner),records)
 if row['scene']!=npc['world']:raise ValueError('Current synthesis NPC world')
