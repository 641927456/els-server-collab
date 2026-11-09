"""Native EE/F4/FA guild task actions and Myu interaction on the actual scene."""
from contextlib import closing
import sqlite3,time
from els_server.domain import guild_quests
from els_server.storage.seal_quests import QuestState,ensure,_state
from els_server.storage.inventory_state import load_items

def store(s):
 from els_server.domain.guild_system_flow import capture
 same,scene_guard=capture(s)
 def guard(db):
  scene_guard(db)
  from els_server.storage.guild_membership_state import snapshot
  if snapshot(db,s.account.uid,s.account.account_id)is None:raise ValueError('Guild quest membership retired')
 return QuestState(s.account.store.path,s.account.uid,account_id=s.account.account_id,account_source_guard=guard),same

def dialogue(s,event,sequence):
 from els_server.protocol import tutorial_dialogue_messages as wire
 if wire.request(event.payload)!=10045:return None
 if event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 0<sequence<2**32:raise ValueError('Guild Myu native envelope')
 selected,same=store(s)
 if s.phase!='guild_agit_ready':
  from els_server.domain.guild_task35630 import catalog
  if str(s.active_map)not in catalog()['towns']:raise ValueError('Myu is not in the actual town')
 from els_server.storage.guild_quests import record
 with closing(sqlite3.connect(selected.path,timeout=10))as db,db:
  db.execute('BEGIN IMMEDIATE');selected.account_source_guard(db);ensure(db)
  active=[r for r in _state(db,selected.uid,load_items(db,selected.uid))['active']if guild_quests.contains(r['id'])and any(sub['m_eClearType']==1 for sub in (guild_quests.catalog()['subquests'][str(i)]for i in r['objectives']))]
  if not active:return []if s.phase=='guild_agit_ready'else None
  operation=s.shop_session_id+':guild-quest-talk:'+str(selected.uid)+':'+str(sequence)
  events=record(db,selected.uid,operation,[(1,1,0)],int(time.time()))
  selected.account_source_guard(db)
  return events
