"""Account-period mark18007 entitlement; never a permanent custom book."""
from contextlib import closing
from pathlib import Path
import sqlite3,struct,time
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.ariel_attendance_messages import text,date
from els_server.storage import ariel_cash as cash,ariel_attendance as attendance

MARK=18007
SLOTS=frozenset((7,8,13,14))
TABLE='ariel_mark_selections'
def value(state):
    if not state['active']:raise ValueError('Ariel mark requires active account period')
    return dict(custom_id=MARK,ability=0,date1=date(state['starts_at']),date2=date(state['expires_at']),variant=1)
def info(v):
    if set(v)!={'custom_id','ability','date1','date2','variant'}or(v['custom_id'],v['ability'],v['variant'])!=(MARK,0,1):raise ValueError('Ariel mark native tuple')
    return struct.pack('>ii',MARK,0)+text(v['date1'])+text(v['date2'])+struct.pack('>i',1)
def selection(values):
    if set(values)-SLOTS:raise ValueError('Ariel mark native selected slot')
    return struct.pack('>I',len(values))+b''.join(bytes([slot])+info(v)for slot,v in sorted(values.items()))
def registered(state):return Event(0x201,kind=0x4cd,payload=bytes(4)+bytes([7])+info(value(state)))
def acknowledged(values=None,result=0):return Event(0x201,kind=0x4cc,payload=struct.pack('>i',result)+selection(values or {}))
def notice(uid,title,values):
    return Event(0x201,kind=0x18e,payload=struct.pack('>QIiI',uid,0,title,len(values))+b''.join(bytes([slot])+struct.pack('>I',1)+info(v)for slot,v in sorted(values.items())))
def selected(db,account,uid,state):
    attendance.owner(db,account,uid)
    rows=db.execute('SELECT account_id,slot,purchase_id FROM ariel_mark_selections WHERE owner=? ORDER BY slot',(uid,)).fetchall()if cash.present(db,TABLE)else []
    if any(a!=account or s not in SLOTS or not isinstance(p,str)for a,s,p in rows):raise ValueError('Saved Ariel mark ownership/source')
    return {s:value(state)for a,s,p in rows if state['active']and p==state['purchase_id']}
def clear_ordinary(db,owner,slot):
    # Called only inside an accepted NEW ordinary custom selection transaction.
    if not db.in_transaction:raise ValueError('Ariel mark clear requires same custom transaction')
    if slot in SLOTS and cash.present(db,TABLE):db.execute('DELETE FROM ariel_mark_selections WHERE owner=? AND slot=?',(owner,slot))
def handle(s,event,sequence):
    if(event.event_id!=0x202 or event.kind!=0x4cb or len(event.payload)<9
       or struct.unpack_from('>i',event.payload,5)[0]!=MARK):return None
    from els_server.domain.ariel_attendance_flow import context,validate
    try:
        captured=context(s)
        if(event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
           or event.payload[:4]!=struct.pack('>I',1)or event.payload[4]not in SLOTS):raise ValueError('Ariel mark native request')
        uid=s.account.uid;account=s.account.account_id;slot=event.payload[4]
        key,hashed=attendance._request_key(s.shop_session_id,uid,sequence,0x4cb,event.payload)
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            try:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate(s,captured);attendance.owner(db,account,uid)
                moment=attendance.clock(time.time);state=attendance.state(db,account,moment);v=value(state)
                if event.payload!=selection({slot:v}):raise ValueError('Ariel mark tuple differs from authoritative account period')
                old=cash.previous(db,key,account,'native:ariel-mark',hashed)
                current=selected(db,account,uid,state)
                values={slot:v}if old is None else ({slot:current[slot]}if slot in current else {})
                from els_server.storage.titles import snapshot as title_snapshot
                title=title_snapshot(db,uid,moment)['title'];events=[acknowledged(values),notice(uid,title,values)]
                for e in events:encode_event(e)
                validate(s,captured)
                if old is None:
                    db.execute('CREATE TABLE IF NOT EXISTS ariel_mark_selections (owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,slot INTEGER NOT NULL CHECK(slot IN (7,8,13,14)),purchase_id TEXT NOT NULL REFERENCES ariel_attendance_periods(purchase_id),PRIMARY KEY(owner,slot))')
                    db.execute('INSERT INTO ariel_mark_selections VALUES (?,?,?,?) ON CONFLICT(owner,slot)DO UPDATE SET account_id=excluded.account_id,purchase_id=excluded.purchase_id',(uid,account,slot,state['purchase_id']))
                    cash.record(db,key,account,'native:ariel-mark',hashed,dict(owner=uid,slot=slot,purchase_id=state['purchase_id']),moment)
                db.commit();return events
            except BaseException:db.rollback();raise
    except ValueError:return [acknowledged(result=-1)]
def project(s,events):
    from els_server.domain.ariel_attendance_flow import authority
    authority(s);events=list(events)
    with cash.reading(s.account.store.path)as db:
        moment=attendance.clock(time.time);state=attendance.state(db,s.account.account_id,moment);values=selected(db,s.account.account_id,s.account.uid,state)
        extra=[]
        if state['active']and any(e.kind==0x2a for e in events):extra.append(registered(state))
        if values:
            from els_server.storage.titles import snapshot as title_snapshot
            extra.append(notice(s.account.uid,title_snapshot(db,s.account.uid,moment)['title'],values))
        for e in extra:encode_event(e)
        authority(s);return events+extra

def economy(db,owner,source):
    """Exact current socket47846: DCB clear EXP only, never kill EXP or ED."""
    if source!='clear':return dict(experience_rate=0.0)
    if not cash.present(db,attendance.TABLE)or not cash.present(db,TABLE):return dict(experience_rate=0.0)
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if row is None:return dict(experience_rate=0.0)
    moment=attendance.clock(time.time);state=attendance.state(db,row[0],moment)
    values=selected(db,row[0],owner,state)
    if not values:return dict(experience_rate=0.0)
    return dict(experience_rate=.2,custom_id=MARK,item_template=482066,socket_id=47846,purchase_id=state['purchase_id'],expires_at=state['expires_at'],native_field='m_fIncreaseDCBExpPercent',DUNGEON_ONLY=1)
