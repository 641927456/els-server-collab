"""Marriage commit at mutual consent; the original client owns the ceremony."""
import json,sqlite3,time
from contextlib import closing
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import weddings
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.domain.relationship_rules import VOW_HALL

TABLE='native_wedding_ceremonies'
SCHEMA='''CREATE TABLE native_wedding_ceremonies(
    reservation INTEGER PRIMARY KEY REFERENCES native_wedding_bookings(id),
    pair_id TEXT NOT NULL,at INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN('ceremony','deadline')),roster_json TEXT NOT NULL)'''


def present(db):
    row=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
    if row is not None and row[0]!=SCHEMA:raise ValueError('Unknown wedding ceremony schema')
    return row is not None


def initialize(db):
    if not db.in_transaction:raise ValueError('Wedding ceremony requires writer')
    if not present(db):db.execute(SCHEMA)


def marriage(db,pair_id):
    if not weddings.present(db):return None
    rows=db.execute('SELECT id,finished_at FROM native_wedding_bookings WHERE pair_id=?'
                    'AND finished_at IS NOT NULL AND canceled_at IS NULL ORDER BY finished_at,id',(pair_id,)).fetchall()
    if not rows:return None
    if not present(db):raise ValueError('Marriage has no original completion source')
    first=rows[0][1];refresh=first
    for reservation,at in rows:
        source=db.execute('SELECT pair_id,at,mode FROM native_wedding_ceremonies WHERE reservation=?',(reservation,)).fetchone()
        if source is None or source[:2]!=(pair_id,at):raise ValueError('Marriage completion source differs from reservation')
        if source[2]=='ceremony':refresh=at
    return dict(married_at=first,refreshed_at=refresh)


def _record(db,row,at,mode,roster):
    initialize(db)
    db.execute('INSERT INTO native_wedding_ceremonies VALUES(?,?,?,?,?)',
               (row['id'],row['pair_id'],at,mode,weddings._json(roster)))
    if db.execute('''UPDATE native_wedding_bookings SET started_at=?,finished_at=?
        WHERE id=?AND started_at IS NULL AND finished_at IS NULL AND canceled_at IS NULL''',
        (at if mode=='ceremony'else None,at,row['id'])).rowcount!=1:
        raise ValueError('Wedding already started, completed or canceled')
    from els_server.storage.wedding_titles import synchronize
    for owner in (row['groom'],row['bride']):synchronize(db,owner,at)


def start(db,reservation,roster,*,now,guard,encode):
    """Caller freezes the actual room, both current spouses and their consent.

    The roster is server state, never a client-selected reward vector. One
    transaction consumes the personalized tickets, saves marriage and issues
    the fixed participation letters before any424 or mailbox is published.
    """
    if not db.in_transaction:raise ValueError('Wedding start requires writer')
    guard(db);row=weddings._record(db,reservation)
    saved,_=weddings.pairing(db,row['owner'],row['account_id'])
    if saved['pair_id']!=row['pair_id']:raise ValueError('Wedding couple generation ended')
    if not 2<=len(roster)<=32 or len({r['uid']for r in roster})!=len(roster)or len({r['account']for r in roster})!=len(roster):
        raise ValueError('Wedding current roster capacity/identities')
    if row['hall']==VOW_HALL and len(roster)!=2:
        raise ValueError('Vow requires exactly two partners')
    if {r['uid']for r in roster if r['role']in(1,2)}!={row['groom'],row['bride']}:
        raise ValueError('Both spouses must consent inside their current room')
    if present(db):
        old=db.execute('SELECT pair_id,mode,roster_json FROM native_wedding_ceremonies WHERE reservation=?',(reservation,)).fetchone()
        if old is not None:
            if old!=(row['pair_id'],'ceremony',weddings._json(roster)):
                raise ValueError('Conflicting wedding ceremony replay')
            answer=encode(row,{r['uid']:()for r in roster},True)
            for messages in answer.values():
                for event in messages:encode_event(event)
            guard(db)
            return answer
    if not row['ends_at']-86340<=now<row['ends_at']+60:
        raise ValueError('Wedding outside its reserved24hour window')
    before={};tickets={}
    for participant in roster:
        uid,account,role=participant['uid'],participant['account'],participant['role']
        require_active_character(db,uid);require_owner(db,uid,account)
        if role not in(1,2,3,4)or role==1 and uid!=row['groom']or role==2 and uid!=row['bride']:
            raise ValueError('Wedding saved actor role')
        if role in(1,2,3):
            if role==3 and db.execute('SELECT 1 FROM native_wedding_invites WHERE reservation=?AND guest=?',(reservation,uid)).fetchone()is None:
                raise ValueError('Wedding invited actor entitlement missing')
            before[uid]=load_items(db,uid)
            tickets[uid]=weddings.owned_ticket(db,uid,reservation,277152 if role==3 else weddings.spouse_ticket(row),
                ticket=participant['ticket'],now=now,items=before[uid])
        elif uid in(row['groom'],row['bride']):raise ValueError('Spouse cannot claim public guest reward')
    from els_server.storage.inventory_actions import _identity,_commit
    changes={r['uid']:()for r in roster};after={}
    for uid,ticket in tickets.items():
        remove(db,uid,ticket);after[uid]=load_items(db,uid)
        position=(ticket['group'],ticket['slot'])
        changes[uid]=((position,next((i for i in after[uid]if(i['group'],i['slot'])==position),None)),)
        operation=f'wedding-start:{reservation}:{uid}'
        _,digest=_identity(uid,0x422,weddings._json(roster).encode(),operation)
        _commit(db,operation,digest,uid,0x422,[position],before[uid],after[uid])
    _record(db,row,now,'ceremony',roster)
    row=weddings._record(db,reservation)
    from els_server.storage.relationship_mail import ceremony
    ceremony(db,row,roster,now)
    answer=encode(row,changes,False)
    for messages in answer.values():
        for event in messages:encode_event(event)
    guard(db)
    if any(load_items(db,uid)!=items for uid,items in after.items()):
        raise ValueError('Wedding ticket state changed before marriage commit')
    if weddings.pairing(db,row['owner'],row['account_id'])[0]['pair_id']!=row['pair_id']:
        raise ValueError('Wedding pair changed before marriage commit')
    return answer


def expire(db,owner,account,*,now,guard,saved=None):
    """The stated24hour fallback changes marriage, without ceremony rewards.

    An unperformed reminder is not a fresh ceremony and cannot renew existing
    buff/title dates. marriage() uses only real ceremonies for later refreshes.
    """
    if not db.in_transaction:raise ValueError('Wedding expiry requires writer')
    guard(db);require_active_character(db,owner);require_owner(db,owner,account)
    if saved is None:saved,_=weddings.pairing(db,owner,account)
    if not weddings.present(db):return ()
    ids=[r[0]for r in db.execute('''SELECT id FROM native_wedding_bookings WHERE pair_id=?
        AND finished_at IS NULL AND canceled_at IS NULL AND ends_at+60<=? ORDER BY id''',(saved['pair_id'],now))]
    marriages=[]
    for reservation in ids:
        row=weddings._record(db,reservation)
        if row['hall']==VOW_HALL:
            db.execute('UPDATE native_wedding_bookings SET canceled_at=? WHERE id=?',(row['ends_at']+60,reservation))
        else:
            _record(db,row,row['ends_at']+60,'deadline',())
            marriages.append(reservation)
    guard(db)
    return tuple(marriages)


def maintenance(path,owner,account):
    """Before original cold restore, settle earned deadlines for this owner."""
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        if not weddings.present(db):return ()
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        from els_server.storage.relationships import snapshot
        saved=snapshot(db,owner,account)
        if saved is None:return ()
        return expire(db,owner,account,now=int(time.time()),guard=lambda db:None,saved=saved)
