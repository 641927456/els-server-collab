"""Durable local solo challenge attempts, using captured phase prerequisites.

Completion runs in RewardState's existing transaction so an encoding error
cannot commit progress without its clear receipt, or vice versa.
"""
import sqlite3,time,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid

def phase_definition(challenge,phase):
 from els_server.domain.dungeon_routes import route_catalog
 found=next((p for p in route_catalog()._data['challenges'] if (p['challenge'],p['phase'])==(challenge,phase)),None)
 if found is None:raise ValueError('Unknown current challenge phase')
 return found

def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS challenge_attempts (uid INTEGER PRIMARY KEY, attempt TEXT NOT NULL, challenge INTEGER NOT NULL, phase INTEGER NOT NULL, deadline INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0)')

def read(db,uid):
 row=db.execute('SELECT attempt,challenge,phase,deadline,progress,complete FROM challenge_attempts WHERE uid=?',(uid,)).fetchone()
 if row is None:return None
 state=dict(zip(('attempt','challenge','phase','deadline','progress','complete'),row));p=phase_definition(state['challenge'],state['phase'])
 mask=0
 for n in p['nodes']:mask|=((1<<n['count'])-1)<<n['flag']
 if (str(uuid.UUID(state['attempt']))!=state['attempt'] or type(state['deadline']) is not int or not 0<state['deadline']<2**63
     or type(state['progress']) is not int or not 0<=state['progress']<=mask or state['progress']&~mask or state['complete'] not in (0,1)):raise ValueError('Invalid persisted challenge state')
 if state['complete'] and not any(n['final'] and state['progress']&(1<<n['flag']) for n in p['nodes']):raise ValueError('Incomplete persisted challenge marked complete')
 return state

def eligible(state,identity,now):
 if not state or state['complete'] or now>=state['deadline']:return None
 p=phase_definition(state['challenge'],state['phase'])
 n=next((n for n in p['nodes'] if n['dungeon']==identity),None)
 if n is None:return None
 mask=((1<<n['count'])-1)<<n['flag']
 if state['progress']&n['requires']!=n['requires'] or state['progress']&mask==mask:return None
 return n

def commit_clear(db,uid,effect):
 ensure(db);state=read(db,uid)
 if not state or state['attempt']!=effect['attempt']:raise ValueError('Challenge attempt changed before settlement')
 node=eligible(state,effect['dungeon'],effect['now'])
 if node is None:raise ValueError('Challenge prerequisite, deadline or completion changed')
 bit=next(1<<(node['flag']+i) for i in range(node['count']) if not state['progress']&(1<<(node['flag']+i)))
 progress=state['progress']|bit
 db.execute('UPDATE challenge_attempts SET progress=?,complete=? WHERE uid=?',(progress,int(bool(node['final'])),uid))

class ChallengeState:
 def __init__(self,path,uid,*,clock=time.time):
  self.path=Path(path);self.uid=character_uid(uid);self.clock=clock
  with closing(self.connect()) as db,db:ensure(db)
 def connect(self):return sqlite3.connect(self.path,timeout=10)
 def current(self):
  with closing(self.connect()) as db:return read(db,self.uid)
 def _guard(self,db,account_id,prepare):
  if prepare is not None:prepare()
  if account_id is not None:
   from els_server.storage.profession_state import require_owner
   from els_server.storage.item_actor import require_active_character
   require_owner(db,self.uid,account_id);require_active_character(db,self.uid)
 def begin(self,challenge,phase,*,account_id=None,prepare=None,precommit=None):
  definition=phase_definition(challenge,phase);now=int(self.clock())
  with closing(self.connect()) as db,db:
   db.execute('BEGIN IMMEDIATE');self._guard(db,account_id,prepare);state=read(db,self.uid)
   if state and not state['complete'] and state['deadline']>now:
    if (state['challenge'],state['phase'])!=(challenge,phase):raise ValueError('Give up the active challenge before switching phases')
   else:
    db.execute('INSERT INTO challenge_attempts VALUES (?,?,?,?,?,0,0) ON CONFLICT(uid) DO UPDATE SET attempt=excluded.attempt,challenge=excluded.challenge,phase=excluded.phase,deadline=excluded.deadline,progress=0,complete=0',(self.uid,str(uuid.uuid4()),challenge,phase,now+definition['seconds']))
    state=read(db,self.uid)
   if precommit is not None:precommit(state)
   self._guard(db,account_id,prepare)
   return state
 def admit(self,identity):
  state=self.current()
  if eligible(state,identity,int(self.clock())) is None:return None
  return dict(attempt=state['attempt'],dungeon=identity)
 def abandon(self,*,account_id=None,prepare=None,precommit=None):
  with closing(self.connect()) as db,db:
   db.execute('BEGIN IMMEDIATE');self._guard(db,account_id,prepare)
   db.execute('DELETE FROM challenge_attempts WHERE uid=?',(self.uid,))
   if precommit is not None:precommit(None)
   self._guard(db,account_id,prepare)
