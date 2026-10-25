"""Local assessment and independent Artifact EXP share the ordinary clear receipt."""
import json,sqlite3,time
from contextlib import closing
from els_server.domain.local_artifact_rules import policy,identity,rating,experience,integer

def modifier(db,owner,source,category,bonus_bp,expires_at):
 """Trusted server-side effect adapter. No client endpoint grants modifiers."""
 if not db.in_transaction or not isinstance(source,str) or not 1<=len(source)<=100:raise ValueError('Modifier transaction/source')
 if category not in ('medal','synergy'):raise ValueError('Artifact modifier category')
 integer(owner,1001,2**63-1,'Owner');integer(expires_at,1,2**63-1,'Modifier expiry')
 limit=policy()['experience']['maximum_medal_bp'] if category=='medal' else policy()['experience']['synergy_bp']
 integer(bonus_bp,0,limit,'Modifier bonus')
 if category=='synergy' and bonus_bp!=limit:raise ValueError('Native synergy magnitude')
 db.execute('CREATE TABLE IF NOT EXISTS artifact_xp_modifiers (owner INTEGER NOT NULL,source TEXT NOT NULL,category TEXT NOT NULL,bonus_bp INTEGER NOT NULL,expires_at INTEGER NOT NULL,PRIMARY KEY(owner,source))')
 db.execute('INSERT INTO artifact_xp_modifiers VALUES (?,?,?,?,?) ON CONFLICT(owner,source) DO UPDATE SET category=excluded.category,bonus_bp=excluded.bonus_bp,expires_at=excluded.expires_at',(owner,source,category,bonus_bp,expires_at))

def validate_assessment(value):
 if not isinstance(value,dict):raise ValueError('Clear assessment')
 expected=rating(value['dungeon'],value['seconds'],value['stages'],value['hostiles'],value['bosses'])
 if value!=expected:raise ValueError('Clear assessment does not match local policy')
 return expected

def commit(db,owner,run_id,assessment,base_exp,now=None):
 if not db.in_transaction:raise ValueError('Clear rule transaction required')
 assessment=validate_assessment(assessment);integer(base_exp,0,2**31-1,'Independent Artifact base EXP')
 from els_server.storage.seal_quests import load_character
 # Historic protocol-only stores have no Characters subsystem. They may
 # retain a clear rating but cannot gain Artifact EXP or create a character.
 has_characters=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone()
 character=load_character(db,owner) if has_characters and db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone() else {}
 now=int(time.time()) if now is None else now;integer(now,0,2**63-1,'Clear time')
 active=[]
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_xp_modifiers'").fetchone():
  active=list(db.execute('SELECT category,bonus_bp FROM artifact_xp_modifiers WHERE owner=? AND expires_at>?',(owner,now)))
 kill=base_exp*policy()['experience']['kill_share_bp']//10000
 xp=experience(character,base_exp-kill,kill,medals=[v for c,v in active if c=='medal'],synergy=any(c=='synergy' for c,v in active))
 if xp['total']:
  from els_server.storage.artifact_progression import grow
  grow(db,owner,xp['total'])
 db.execute('CREATE TABLE IF NOT EXISTS local_dungeon_assessments (run_id TEXT NOT NULL,owner INTEGER NOT NULL,assessment_json TEXT NOT NULL,artifact_xp_json TEXT NOT NULL,PRIMARY KEY(run_id,owner))')
 db.execute('INSERT INTO local_dungeon_assessments VALUES (?,?,?,?)',(run_id,owner,json.dumps(assessment,sort_keys=True),json.dumps(xp,sort_keys=True)))
 return xp

def lookup_db(db,owner,run_id):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_dungeon_assessments'").fetchone():return None
 row=db.execute('SELECT assessment_json,artifact_xp_json FROM local_dungeon_assessments WHERE run_id=? AND owner=?',(run_id,owner)).fetchone()
 return dict(assessment=json.loads(row[0]),artifact_experience=json.loads(row[1])) if row else None

def lookup(path,owner,run_id):
 with closing(sqlite3.connect(path,timeout=10)) as db:return lookup_db(db,owner,run_id)
