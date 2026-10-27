"""Character-owned page snapshots; canonical old tables remain the active page.

Expansion/debit/receipt and selection/snapshot/ACK preparation share one real
SQLite transaction. No player database is copied or replaced by this module.
"""
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
import hashlib,json,sqlite3,struct
from els_server.domain.ordinary_skill_pages import POLICY,MAX_PAGES,EXPAND_ED

def present(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()is not None

def meta(db,owner):
 row=db.execute('SELECT page_count,selected,revision FROM ordinary_skill_page_states WHERE owner=?',(owner,)).fetchone()if present(db,'ordinary_skill_page_states')else None
 if row is None:return dict(count=1,selected=1,revision=0)
 count,selected,revision=row
 if any(type(v)is not int for v in row)or not 1<=selected<=count<=MAX_PAGES or not 0<=revision<2**63:raise ValueError('Corrupt ordinary page state')
 return dict(count=count,selected=selected,revision=revision)

def selected_page(db,owner):return meta(db,owner)['selected']

def _pairs(pairs):
 if len(pairs) not in (3,11) or any(not isinstance(p,(tuple,list))or len(p)!=2 or any(type(v)is not int for v in p)for p in pairs):raise ValueError('Saved ordinary force layout')
 if any((s==0)!=(r==0)or s<0 or r not in(0,3,4,5,6)for s,r in pairs):raise ValueError('Saved ordinary force rank')
 return [list(p)for p in pairs]+[[0,0]]*(11-len(pairs))

def _load(row):
 raw,traits,force=row
 if type(raw)is not bytes or len(raw)!=88:raise ValueError('Saved ordinary page slots')
 values=list(struct.unpack('>22i',raw))
 if any(v<0 for v in values)or len([v for v in values if v])!=len({v for v in values if v}):raise ValueError('Saved ordinary page duplicate/negative')
 traits=json.loads(traits);force=json.loads(force)
 if type(traits)is not dict or len(traits)>1000:raise ValueError('Saved ordinary page traits')
 normalized={}
 for k,n in traits.items():
  if not k.isdigit()or str(int(k))!=k or int(k)<1 or type(n)is not int or not 1<=n<=22:raise ValueError('Saved ordinary page trait identity')
  normalized[int(k)]=n
 return dict(slots=values,traits=normalized,force=_pairs(force))

def view(db,owner):
 state=meta(db,owner);pages={}
 if state['count']>1:
  if not present(db,'ordinary_skill_page_snapshots'):raise ValueError('Missing ordinary pages')
  for page,raw,traits,force in db.execute('SELECT page,slots,traits,forces FROM ordinary_skill_page_snapshots WHERE owner=? ORDER BY page',(owner,)):
   if type(page)is not int or not 1<=page<=state['count']:raise ValueError('Saved ordinary page ownership')
   pages[page]=_load((raw,traits,force))
  if any(p not in pages for p in range(1,state['count']+1)if p!=state['selected']):raise ValueError('Missing inactive ordinary page')
 return dict(state,pages=pages)

def ensure(db):
 if not db.in_transaction:raise ValueError('Ordinary pages require caller transaction')
 db.execute('CREATE TABLE IF NOT EXISTS ordinary_skill_page_states(owner INTEGER PRIMARY KEY REFERENCES characters(uid),page_count INTEGER NOT NULL CHECK(page_count BETWEEN 1 AND 3),selected INTEGER NOT NULL CHECK(selected BETWEEN 1 AND page_count),revision INTEGER NOT NULL CHECK(revision>=0))')
 db.execute('CREATE TABLE IF NOT EXISTS ordinary_skill_page_snapshots(owner INTEGER NOT NULL REFERENCES characters(uid),page INTEGER NOT NULL CHECK(page BETWEEN 1 AND 3),slots BLOB NOT NULL CHECK(length(slots)=88),traits TEXT NOT NULL,forces TEXT NOT NULL,PRIMARY KEY(owner,page))')
 db.execute('CREATE TABLE IF NOT EXISTS ordinary_skill_page_receipts(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),kind INTEGER NOT NULL,proof TEXT NOT NULL)')

def _save_snapshot(db,owner,page,slots,traits,force):
 db.execute('INSERT INTO ordinary_skill_page_snapshots VALUES(?,?,?,?,?) ON CONFLICT(owner,page)DO UPDATE SET slots=excluded.slots,traits=excluded.traits,forces=excluded.forces',(owner,page,struct.pack('>22i',*slots),json.dumps(traits,sort_keys=True,separators=(',',':')),json.dumps(_pairs(force),separators=(',',':'))))

def _actor(db,owner,account):
 #Existing authoritative projection includes lifecycle, ownership, learned/seal
 #qualifications, row expansion, artifact gate, owned forces and selected slots.
 from els_server.storage.boosting_2026_force_equipment import _character
 return _character(db,owner,account)

def _current_slots(db,owner,c):
 from els_server.storage.local_state import LocalState
 return LocalState._load_skills(SimpleNamespace(uid=owner),db,c)

def _reply(db,owner,account,kind):
 from els_server.protocol.protocol_codec import encode_event,Event
 from els_server.domain.ordinary_skill_pages import expanded,selected
 from els_server.domain.skill_state import initialization_payload
 from els_server.domain.skill_rules import equippable_skills,learned_skills
 c=_actor(db,owner,account);state=view(db,owner);c['ordinary_skill_pages']=state
 slots=_current_slots(db,owner,c);ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
 events=[expanded(ed,state['count'])]if kind==0x481 else [selected(c,slots,state['selected'])]
 events.append(Event(0x201,kind=0x55b,payload=initialization_payload(slots,owner,equippable_skills(c),learned_skills(c),c)))
 for event in events:encode_event(event)
 return events

def action(path,owner,account,kind,payload,operation,*,validate):
 from els_server.domain.ordinary_skill_pages import request,page_character,page_slots
 from els_server.storage.item_actor import require_active_character
 target=request(kind,payload)
 if type(operation)is not str or not 1<=len(operation)<=160:raise ValueError('Ordinary page receipt identity')
 proof=hashlib.sha256(POLICY.encode()+struct.pack('>QQH',owner,account,kind)+payload).hexdigest()
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate();require_active_character(db,owner)
  c=_actor(db,owner,account);state=view(db,owner)
  old=db.execute('SELECT owner,kind,proof FROM ordinary_skill_page_receipts WHERE operation=?',(operation,)).fetchone()if present(db,'ordinary_skill_page_receipts')else None
  if old is not None:
   if old!=(owner,kind,proof):raise ValueError('Conflicting ordinary page receipt')
   events=_reply(db,owner,account,kind);validate();require_active_character(db,owner);return events
  if state['revision']>=2**63-1:raise ValueError('Ordinary page revision overflow')
  if kind==0x481:
   if state['count']>=MAX_PAGES:raise ValueError('Ordinary page local maximum')
   balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
   if balance is None or balance[0]<EXPAND_ED or balance[1]>=2**63-1:raise ValueError('Ordinary page funds/revision')
   ensure(db);count=state['count']+1
   _save_snapshot(db,owner,count,(0,)*22,{},((0,0),)*3)
   db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?',(EXPAND_ED,owner))
   db.execute('INSERT INTO ordinary_skill_page_states VALUES(?,?,?,?) ON CONFLICT(owner)DO UPDATE SET page_count=excluded.page_count,revision=excluded.revision',(owner,count,state['selected'],state['revision']+1))
  elif target!=state['selected']:
   if target>state['count']:raise ValueError('Unowned ordinary page')
   from els_server.storage.skill_traits import saved as traits
   from els_server.storage.boosting_2026_force_equipment import saved as force
   saved=state['pages'][target];incoming=page_character(c,saved);slots=page_slots(incoming,saved)
   ensure(db);_save_snapshot(db,owner,state['selected'],_current_slots(db,owner,c),traits(db,owner),force(db,owner))
   from els_server.storage.local_state import LocalState
   LocalState._save_skills(SimpleNamespace(uid=owner),db,slots,incoming)
   if present(db,'character_skill_traits'):
    db.execute('DELETE FROM character_skill_traits WHERE owner=?',(owner,))
   if incoming['skill_traits']:
    db.execute('CREATE TABLE IF NOT EXISTS character_skill_traits(owner INTEGER NOT NULL REFERENCES characters(uid),skill INTEGER NOT NULL CHECK(skill>0),note INTEGER NOT NULL CHECK(note BETWEEN 1 AND 22),revision INTEGER NOT NULL,PRIMARY KEY(owner,skill))')
    from els_server.domain.skill_traits import validate as validate_trait
    for skill,note in incoming['skill_traits'].items():
     #The full dormant snapshot was projected through current native trait
     #definitions; only current valid choices enter the canonical table.
     validate_trait(incoming,skill,note)
     db.execute('INSERT INTO character_skill_traits VALUES(?,?,?,1)',(owner,skill,note))
   if present(db,'selected_2026_force_slots'):db.execute('DELETE FROM selected_2026_force_slots WHERE owner=?',(owner,))
   force_values=incoming['force_slots']
   if any(s for s,r in force_values):
    if not present(db,'selected_2026_force_slots'):raise ValueError('Ordinary page force schema/ownership missing')
    db.executemany('INSERT INTO selected_2026_force_slots VALUES(?,?,?,?)',[(owner,i,s,r)for i,(s,r)in enumerate(force_values)if s])
   db.execute('UPDATE ordinary_skill_page_states SET selected=?,revision=revision+1 WHERE owner=?',(target,owner))
  else:ensure(db) #Same-page request is a read-only state transition + receipt.
  events=_reply(db,owner,account,kind)
  db.execute('INSERT INTO ordinary_skill_page_receipts VALUES(?,?,?,?)',(operation,owner,kind,proof))
  validate();require_active_character(db,owner)
  return events
