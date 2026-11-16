"""Account-period mark18007 entitlement; never a permanent custom book."""
from contextlib import closing
from pathlib import Path
import sqlite3,struct,time
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.ariel_attendance_messages import text,date
from els_server.storage import ariel_cash as cash,ariel_attendance as attendance

MARK=18007
SLOT=9
SLOTS=frozenset((SLOT,))
# Preserve the existing SQL format; these old keys were incorrectly exposed
# as sit-motion slots. A pointmark has one native slot, independent of sitting.
STORED_SLOT=7
STORED_SLOTS=frozenset((7,8,13,14))
TABLE='ariel_mark_selections'
def empty():
    from els_server.domain.character_custom import canonical
    return canonical(0)
def value(state):
    if not state['active']:raise ValueError('Ariel mark requires active account period')
    return dict(custom_id=MARK,ability=0,date1=date(state['starts_at']),date2=date(state['expires_at']),variant=1)
def info(v):
    if (set(v)!={'custom_id','ability','date1','date2','variant'}or v['custom_id']not in(0,MARK)
        or(v['ability'],v['variant'])!=(0,1)or(v['custom_id']==0 and v!=empty())):raise ValueError('Ariel mark native tuple')
    return struct.pack('>ii',v['custom_id'],0)+text(v['date1'])+text(v['date2'])+struct.pack('>i',1)
def selection(values):
    if set(values)-SLOTS:raise ValueError('Ariel mark native selected slot')
    return struct.pack('>I',len(values))+b''.join(bytes([slot])+info(v)for slot,v in sorted(values.items()))
def registered(state):return Event(0x201,kind=0x4cd,payload=bytes(4)+bytes([SLOT])+info(value(state)))
def acknowledged(values=None,result=0):return Event(0x201,kind=0x4cc,payload=struct.pack('>i',(2856) if result == -1 else result)+selection(values or {}))
def notice(uid,title,values):
    from els_server.protocol.character_custom_messages import selected_notice
    return selected_notice(uid,title,values)
def selected(db,account,uid,state):
    attendance.owner(db,account,uid)
    rows=db.execute('SELECT account_id,slot,purchase_id FROM ariel_mark_selections WHERE owner=? ORDER BY slot',(uid,)).fetchall()if cash.present(db,TABLE)else []
    return _selected_rows(account,rows,state)
def _selected_rows(account,rows,state):
    # The batch reader supplies rows after its shared owner/lifecycle checks.
    if any(a!=account or s not in STORED_SLOTS or not isinstance(p,str)for a,s,p in rows):raise ValueError('Saved Ariel mark ownership/source')
    return {SLOT:value(state)}if any(state['active']and p==state['purchase_id']for a,s,p in rows)else {}
def handle(s,event,sequence):
    if(event.event_id!=0x202 or event.kind!=0x4cb or len(event.payload)<5
       or(event.payload[4]!=SLOT and(len(event.payload)<9 or struct.unpack_from('>i',event.payload,5)[0]!=MARK))):return None
    from els_server.domain.ariel_attendance_flow import context,validate
    try:
        captured=context(s)
        if(event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
           or event.payload[:4]!=struct.pack('>I',1)or event.payload[4]!=SLOT or len(event.payload)<9):raise ValueError('Ariel mark native request')
        requested=struct.unpack_from('>i',event.payload,5)[0]
        # Original 11F48D0 sends default dates for pointmarks, not the account
        # period from 4CD. The server resolves the finite entitlement itself.
        native=empty();native['custom_id']=requested
        variant=struct.unpack_from('>i',event.payload,len(event.payload)-4)[0]
        expected=selection({SLOT:native})if requested in(0,MARK)else b''
        if variant not in(1,2,3)or event.payload!=expected[:-4]+struct.pack('>i',variant):raise ValueError('Ariel mark native Apply tuple')
        uid=s.account.uid;account=s.account.account_id
        key,hashed=attendance._request_key(s.shop_session_id,uid,sequence,0x4cb,event.payload)
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            try:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate(s,captured);attendance.owner(db,account,uid)
                unit=db.execute('SELECT unit_type FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                # Pointmarks are shared appearance; Lu/Ciel's native producer
                # emits side2 (or side3 when clearing Ciel), normalized to shared1.
                allowed=(2,)if requested else(2,3)
                if variant not in(allowed if unit==10 else(1,)):raise ValueError('Ariel mark native character side')
                moment=attendance.clock(time.time);state=attendance.state(db,account,moment)
                old=cash.previous(db,key,account,'native:ariel-mark',hashed)
                current=selected(db,account,uid,state)
                values={SLOT:(value(state)if requested else empty())}if old is None else {SLOT:current.get(SLOT,empty())}
                from els_server.storage.titles import equipped as equipped_title
                from els_server.storage.character_custom import actor_selection
                visible=actor_selection(db,uid,account,moment);visible.pop(SLOT,None)
                if values[SLOT]['custom_id']:visible.update(values)
                title=equipped_title(db,uid,moment);events=[acknowledged(values),notice(uid,title,visible)]
                for e in events:encode_event(e)
                validate(s,captured)
                if old is None:
                    if cash.present(db,TABLE):db.execute('DELETE FROM ariel_mark_selections WHERE owner=?',(uid,))
                    if requested:
                        db.execute('CREATE TABLE IF NOT EXISTS ariel_mark_selections (owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,slot INTEGER NOT NULL CHECK(slot IN (7,8,13,14)),purchase_id TEXT NOT NULL REFERENCES ariel_attendance_periods(purchase_id),PRIMARY KEY(owner,slot))')
                        db.execute('INSERT INTO ariel_mark_selections VALUES (?,?,?,?)',(uid,account,STORED_SLOT,state['purchase_id']))
                    cash.record(db,key,account,'native:ariel-mark',hashed,dict(owner=uid,slot=SLOT,custom_id=requested,purchase_id=state['purchase_id']),moment)
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
        own_notice=any(e.event_id==0x201 and e.kind==0x18e and e.payload[:8]==struct.pack('>Q',s.account.uid)for e in events)
        if values and not own_notice:
            from els_server.storage.titles import equipped as equipped_title
            from els_server.storage.character_custom import actor_selection
            visible=actor_selection(db,s.account.uid,s.account.account_id,moment)
            extra.append(notice(s.account.uid,equipped_title(db,s.account.uid,moment),visible))
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
