"""Ordinary Atma stone synthesis; explicit compatibility family weighting.

Current Lua gives ED/upgrade rates. The four ordinary stone result families
are drawn uniformly by this compatibility-v1 policy; no retail family-weight
claim. Bound/event stones and all accessory-breath recipes remain closed.
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

def quote(selected):
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 c=catalog();grades=set()
 for item,amount in selected:
  require_current(item);require_unlocked(item)
  row=c['items'].get(str(item['template']))
  if row is None or item['group']!=4 or amount>item['count']or item.get('sealed')or item.get('identified')is False:raise ValueError('Unqualified synthesis input')
  grades.add(row['grade'])
 if len(grades)!=1:raise ValueError('Synthesis same quality required')
 grade=grades.pop();recipe=c['recipes'][str(grade)];total=sum(n for _,n in selected)
 return recipe,total//3

def draw(recipe,randbelow):
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
