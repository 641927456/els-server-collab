"""Owned collection slots: native960 selection and962 ED expansion.

Current ElExpeditionSystem.lua fb6e00f3... defines5,000,000ED per slot.
This candidate covers the original free page; paid preset expansion is separate.
"""
import json,sqlite3,struct,time
from contextlib import closing
from pathlib import Path
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.item_actor import require_active_character

TABLE='character_collection_synergy_slots'
EXPAND_ED=5000000
WRITES_ENABLED=True


def choices(value,registered,expansion):
    if not isinstance(value,dict)or len(value)>6:raise ValueError('Synergy slot map')
    allowed={(r['unit_type'],r['line'])for r in registered};result={};seen=set()
    for slot,pair in sorted(value.items()):
        if type(slot)is not int or not 1<=slot<=6 or type(pair)not in (list,tuple)or len(pair)!=2 or any(type(v)is not int for v in pair):raise ValueError('Synergy native slot identity')
        unit,line=pair
        if (unit,line)==(0,0):continue
        if slot>expansion+2 or (unit,line)not in allowed or (unit,line)in seen:raise ValueError('Synergy unowned, locked or duplicate career')
        seen.add((unit,line));result[slot]=(unit,line)
    return result


def state(db,owner,account,registered):
    from els_server.storage.el_search_collection import exists
    if not exists(db,TABLE):return dict(expansion=0,presets={})
    row=db.execute('SELECT account_id,expansion,selection_json,updated_at FROM character_collection_synergy_slots WHERE owner=?',(owner,)).fetchone()
    if row is None:return dict(expansion=0,presets={})
    if row[0]!=account or type(row[1])is not int or not 0<=row[1]<=4 or type(row[3])is not int or row[3]<=0:raise ValueError('Saved synergy slot integrity')
    records=json.loads(row[2])
    if not isinstance(records,list)or len(records)>6 or any(not isinstance(r,list)or len(r)!=3 for r in records):raise ValueError('Saved synergy selection records')
    selected={r[0]:r[1:]for r in records}
    if len(selected)!=len(records):raise ValueError('Saved synergy duplicate slot')
    selected=choices(selected,registered,row[1])
    if records!=[[slot,*pair]for slot,pair in sorted(selected.items())]:raise ValueError('Saved synergy canonical selection')
    return dict(expansion=row[1],presets={1:selected}if selected else{})


def slots_wire(selected):
    return struct.pack('>I',len(selected))+b''.join(struct.pack('>iHH',slot,*pair)for slot,pair in sorted(selected.items()))


def selection_request(payload):
    if not isinstance(payload,bytes)or len(payload)<8:raise ValueError('Native960 selection length')
    count=struct.unpack_from('>I',payload)[0]
    if count>6 or len(payload)!=8+count*8:raise ValueError('Native960 finite slot count')
    selected={};cursor=4
    for _ in range(count):
        slot,unit,line=struct.unpack_from('>iHH',payload,cursor);cursor+=8
        if slot in selected:raise ValueError('Native960 duplicate slot key')
        selected[slot]=(unit,line)
    page=struct.unpack_from('>i',payload,cursor)[0]
    if page!=1:raise ValueError('Only the original free synergy page is qualified')
    return selected


def reply(kind,value,ed,*,result=0):
    if kind==0x962:body=struct.pack('>iiq',result,value['expansion'],ed);response=0x963
    elif kind==0x960:body=struct.pack('>i',result)+slots_wire(value['presets'].get(1,{}))+struct.pack('>i',1);response=0x961
    else:raise ValueError('Synergy original request family')
    return Event(0x201,kind=response,payload=body)


def perform(path,owner,account,kind,payload,operation,guard):
    if kind not in (0x960,0x962)or not callable(guard):raise ValueError('Synergy transaction entry')
    if kind==0x962:
        if payload:raise ValueError('Native962 original empty request')
        selected=None
    else:selected=selection_request(payload)
    owner,digest=_identity(owner,kind,str(account).encode()+b':collection-synergy:'+payload,operation)
    from els_server.storage.el_search_collection import snapshot,identity
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner);identity(db,owner,account)
        old=_previous(db,operation,digest);current=snapshot(db,owner,account)
        if current is None or not current['active']:raise ValueError('Open the collection before changing synergy slots')
        ed,revision=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if old is not None:
            event=reply(kind,current,ed);encode_event(event);guard(db);return[event]
        if not WRITES_ENABLED:raise ValueError('Collection synergy writer held')
        if not 0<=revision<2**63-1:raise ValueError('Synergy balance revision')
        expansion=current['expansion'];saved=current['presets'].get(1,{})
        if kind==0x962:
            if expansion>=4 or ed<EXPAND_ED:raise ValueError('Synergy maximum slots or insufficient ED')
            expansion+=1;ed-=EXPAND_ED
        else:saved=choices(selected,current['registered'],expansion)
        db.execute('CREATE TABLE IF NOT EXISTS character_collection_synergy_slots (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),expansion INTEGER NOT NULL CHECK(expansion BETWEEN 0 AND 4),selection_json TEXT NOT NULL,updated_at INTEGER NOT NULL CHECK(updated_at>0))')
        records=json.dumps([[slot,*pair]for slot,pair in sorted(saved.items())],separators=(',',':'))
        db.execute('INSERT INTO character_collection_synergy_slots VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET expansion=excluded.expansion,selection_json=excluded.selection_json,updated_at=excluded.updated_at',(owner,account,expansion,records,int(time.time())))
        db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=?',(ed,owner))
        current=snapshot(db,owner,account);event=reply(kind,current,ed);encode_event(event)
        guard(db);_commit(db,operation,digest,owner,kind,[],[],[])
        return[event]


DROP_FACTS='collection_drop_facts'

def effect_snapshot(db,owner):
    from els_server.storage.el_search_collection import snapshot,exists,ACT
    from els_server.storage.bank_state import account_for
    if not exists(db,ACT)or not db.execute('SELECT 1 FROM '+ACT+' WHERE owner=?',(owner,)).fetchone():return None
    return snapshot(db,owner,account_for(db,owner))

def drop_bonus(db,owner,identity,operation,context,*,already_issued=False,now=None):
    """Freeze one owned current collection state in the original drop writer."""
    import hashlib
    from els_server.storage.bank_state import account_for
    from els_server.storage.el_search_collection import snapshot,exists
    from els_server.domain.el_search_effects import economic
    from els_server.domain.el_search_effects import eligible
    if not db.in_transaction or type(context)is not dict:raise ValueError('Collection original drop writer')
    account=account_for(db,owner);canonical=json.dumps(context,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(canonical.encode()).hexdigest()
    prior=db.execute('SELECT owner,account_id,dungeon,context_sha256,basis_points,settled_at,snapshot_json FROM collection_drop_facts WHERE operation=?',(operation,)).fetchone()if exists(db,DROP_FACTS)else None
    if prior:
        if prior[:4]!=(owner,account,identity,digest):raise ValueError('Changed collection drop source receipt')
        value=json.loads(prior[6]);value['presets']={int(page):{int(slot):pair for slot,pair in selected.items()}for page,selected in value['presets'].items()}
        frozen=economic(value,now=prior[5])
        if not eligible(identity)or prior[4]!=frozen['drop_bp']or not 0<prior[4]<=1100:raise ValueError('Collection drop exact source percentage')
        return prior[4]
    if already_issued or not WRITES_ENABLED or not eligible(identity):return 0
    when=int(time.time())if now is None else now;value=effect_snapshot(db,owner)
    amount=economic(value,now=when)['drop_bp']
    if not amount:return 0
    db.execute('CREATE TABLE IF NOT EXISTS collection_drop_facts (operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,dungeon INTEGER NOT NULL,context_sha256 TEXT NOT NULL,basis_points INTEGER NOT NULL,settled_at INTEGER NOT NULL,snapshot_json TEXT NOT NULL)')
    db.execute('INSERT INTO collection_drop_facts VALUES(?,?,?,?,?,?,?,?)',(operation,owner,account,identity,digest,amount,when,json.dumps(value,sort_keys=True,separators=(',',':'))))
    return amount
