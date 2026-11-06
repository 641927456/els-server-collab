"""Authoritative local-policy Ariel type3 ledger; native UI/effects are reused."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,time,uuid
from els_server.storage import ariel_cash as cash

TYPE=3
DURATION=30*86400
ACTIVATION_PRICE=488
MAKEUP_PRICE=60
SKU_ACTIVATION=300721049
SKU_MAKEUP=300721051
TABLE='ariel_attendance_periods'
CLAIMS='ariel_attendance_claims'

def day(moment):return (moment-7200)//86400  # Beijing10:00 = UTC02:00.
def next_reset(moment):return (day(moment)+1)*86400+7200
def clock(now):
    value=int(now())
    if not 0<=value<2**40:raise ValueError('Ariel authoritative clock')
    return value
def initialize(db):
    if not db.in_transaction:raise ValueError('Ariel initialization requires transaction')
    db.execute('CREATE TABLE IF NOT EXISTS ariel_attendance_periods (purchase_id TEXT PRIMARY KEY,account_id INTEGER NOT NULL,starts_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,attended INTEGER NOT NULL CHECK(attended>=0 AND attended<=15),last_day INTEGER,revision INTEGER NOT NULL CHECK(revision>=1),UNIQUE(account_id,starts_at))')
    db.execute('CREATE TABLE IF NOT EXISTS ariel_attendance_claims (purchase_id TEXT NOT NULL REFERENCES ariel_attendance_periods(purchase_id),reward_index INTEGER NOT NULL CHECK(reward_index>=0 AND reward_index<15),owner INTEGER NOT NULL REFERENCES characters(uid),item_uids_json TEXT NOT NULL,claimed_at INTEGER NOT NULL,PRIMARY KEY(purchase_id,reward_index))')
def owner(db,account,uid):
    from els_server.storage.profession_state import require_owner
    from els_server.storage.item_actor import require_active_character
    cash.account_id(account);require_owner(db,uid,account);require_active_character(db,uid)
def state(db,account,moment):
    cash.account_id(account)
    row=db.execute('SELECT purchase_id,starts_at,expires_at,attended,last_day,revision FROM ariel_attendance_periods WHERE account_id=? ORDER BY starts_at DESC LIMIT 1',(account,)).fetchone()if cash.present(db,TABLE)else None
    if row is None:return dict(purchase_id=None,starts_at=0,expires_at=0,attended=0,last_day=None,revision=0,claimed=[0]*15,active=False,ready_at=0)
    key,starts,expires,count,last,revision=row
    if(not isinstance(key,str)or any(type(v)is not int for v in(starts,expires,count,revision))
       or not 0<=starts<=moment<2**40 or not starts<expires<2**40 or expires-starts!=DURATION or not 0<=count<=15
       or not 1<=revision<2**63 or(last is not None and(type(last)is not int or not day(starts)<=last<=day(moment)))):
        raise ValueError('Saved Ariel period boundary or future day')
    claims=db.execute('SELECT reward_index FROM ariel_attendance_claims WHERE purchase_id=? ORDER BY reward_index',(key,)).fetchall()if cash.present(db,CLAIMS)else []
    if any(type(i)is not int or not 0<=i<count for(i,)in claims):raise ValueError('Saved Ariel claim boundary')
    claimed=[0]*15
    for(i,)in claims:claimed[i]=1
    return dict(purchase_id=key,starts_at=starts,expires_at=expires,attended=count,last_day=last,revision=revision,claimed=claimed,active=starts<=moment<expires,ready_at=next_reset(moment)if last==day(moment)else 0)
def snapshot(path,account,*,validate=lambda:None,now=time.time):
    validate()
    with cash.reading(path)as db:
        value=state(db,account,clock(now));validate();return value
def _request_key(session,uid,sequence,kind,payload):
    if(not isinstance(session,str)or str(uuid.UUID(session))!=session or uuid.UUID(session).version!=4
       or type(uid)is not int or not 1001<=uid<2**63 or type(sequence)is not int or not 1<=sequence<2**32
       or type(kind)is not int or not isinstance(payload,bytes)or len(payload)>1024):raise ValueError('Ariel operation identity')
    return 'ariel:'+session+':'+str(uid)+':'+str(sequence),cash.digest([uid,kind,payload.hex()])
def _encoded(events):
    from els_server.protocol.protocol_codec import encode_event
    if not isinstance(events,list)or not 1<=len(events)<=32 or sum(len(encode_event(e))for e in events)>1000000:raise ValueError('Ariel precommit response bound')
    return events
def replay_inventory(db,uid,receipt,moment):
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import expired
    if receipt.get('owner')!=uid:raise ValueError('Ariel replay owner')
    ids=receipt.get('item_uids',[])
    if not isinstance(ids,list)or len(ids)>36 or len(set(ids))!=len(ids)or any(type(i)is not int or not 1<=i<2**63 for i in ids):raise ValueError('Ariel replay item identities')
    positions=receipt.get('changed_positions',[])+receipt.get('item_positions',[])
    if any(not isinstance(p,(list,tuple))or len(p)!=2 or any(type(v)is not int for v in p)for p in positions):raise ValueError('Ariel replay positions')
    from els_server.storage.bag_capacity import allowances
    limits=allowances(db,uid)
    if any(g not in limits or not 0<=slot<limits[g]for g,slot in positions):raise ValueError('Ariel replay owned position')
    current=[i for i in load_items(db,uid)if not expired(i,now=moment)]
    at={(i['group'],i['slot']):i for i in current}
    requested={tuple(p)for p in positions}|{(i['group'],i['slot'])for i in current if i['uid']in ids}
    # Each remembered/current position receives its authoritative current item,
    # or an empty record. Never restore a receipt's old count/UID/expiration.
    return [(p,at.get(p))for p in sorted(requested)]

def perform(path,account,uid,session,sequence,kind,payload,request,*,validate,encode,now=time.time):
    """One write-lock/clock/owner/lease/preencoding/receipt boundary per request."""
    key,hashed=_request_key(session,uid,sequence,kind,payload);cash.account_id(account);path=Path(path)
    if not path.is_file():raise ValueError('Ariel state file missing')
    with closing(sqlite3.connect(path,timeout=10))as db:
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate();owner(db,account,uid)
            moment=clock(now);old=cash.previous(db,key,account,'native:'+str(kind),hashed)
            if old is not None:
                current=state(db,account,moment)
                result=dict(replayed=True,items=[],changed=replay_inventory(db,uid,old,moment),products=old.get('products',[]))
                if kind==0x1dd and result['products']==[[SKU_ACTIVATION,1]] and current['active'] and old.get('purchase_id')==current['purchase_id']:result['activated']=current['purchase_id']
                answer=_encoded(encode(db,result,current,cash.balance(db,account)))
                validate();db.commit();return answer
            current=state(db,account,moment);result=dict(replayed=False,items=[],changed=[],products=[])
            if kind==0x1dd:
                products=request
                if not isinstance(products,tuple)or len(products)!=1:raise ValueError('Ariel one qualified product per purchase')
                sku,quantity=products[0]
                if type(quantity)is not int or not 1<=quantity<=15:raise ValueError('Ariel product quantity boundary')
                if sku==SKU_ACTIVATION:
                    if quantity!=1 or current['active']:raise ValueError('Ariel one active period per account')
                    before=cash.balance(db,account);cash.replace(db,account,before,-ACTIVATION_PRICE)
                    initialize(db);period=str(uuid.uuid4())
                    db.execute('INSERT INTO ariel_attendance_periods VALUES (?,?,?,?,0,NULL,1)',(period,account,moment,moment+DURATION))
                    result['activated']=period
                elif sku==SKU_MAKEUP:
                    before=cash.balance(db,account);cash.replace(db,account,before,-MAKEUP_PRICE*quantity)
                    from els_server.storage.inventory_state import grant_items
                    from els_server.domain.ariel_attendance_rules import grant_plan
                    result['items']=grant_items(db,[grant_plan(721051,quantity,moment)],uid)
                else:raise ValueError('Unqualified Ariel cash SKU')
                result['products']=[[sku,quantity]]
            else:
                if not current['active']:raise ValueError('Ariel active account period required')
                count=current['attended']
                if kind==0xc8c:
                    if count>=15 or current['last_day']==day(moment):raise ValueError('Ariel daily attendance unavailable')
                    initialize(db)
                    db.execute('UPDATE ariel_attendance_periods SET attended=attended+1,last_day=?,revision=revision+1 WHERE purchase_id=?',(day(moment),current['purchase_id']))
                elif kind==0xc90:
                    available=min(15,day(moment)-day(current['starts_at'])+int(current['last_day']==day(moment)))
                    if count>=available:raise ValueError('Ariel no missed attendance day')
                    from els_server.storage.inventory_state import load_items
                    from els_server.domain.item_expiration import expired
                    from els_server.domain.item_locks import require_unlocked
                    items=[i for i in load_items(db,uid)if i['template']==721051 and i['group']==4 and not expired(i,now=moment)]
                    if not items:raise ValueError('Ariel owned current makeup coupon required')
                    item=min(items,key=lambda i:(i.get('expires_at',2**63),i['slot'],i['uid']));require_unlocked(item,now=moment)
                    remaining=dict(item,count=item['count']-1)if item['count']>1 else None
                    if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],uid))
                    else:
                        from els_server.storage.item_expiration import forget
                        forget(db,item['uid']);db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],uid))
                    result['changed']=[((item['group'],item['slot']),remaining)]
                    initialize(db);db.execute('UPDATE ariel_attendance_periods SET attended=attended+1,revision=revision+1 WHERE purchase_id=?',(current['purchase_id'],))
                elif kind==0xc8e:
                    index=request
                    if type(index)is not int or not 0<=index<count or current['claimed'][index]:raise ValueError('Ariel reward is unavailable or already claimed')
                    from els_server.storage.inventory_state import grant_items
                    from els_server.domain.ariel_attendance_rules import rewards,grant_plan
                    reward=rewards()[index]
                    result['items']=grant_items(db,[grant_plan(reward['template'],reward['quantity'],moment)],uid)
                    initialize(db);db.execute('INSERT INTO ariel_attendance_claims VALUES (?,?,?,?,?)',(current['purchase_id'],index,uid,cash.canonical([i['uid']for i in result['items']]),moment))
                else:raise ValueError('Unqualified Ariel native operation')
            if result['items']or result['changed']:
                if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision<9223372036854775807',(uid,)).rowcount!=1:
                    raise ValueError('Ariel inventory revision boundary')
            after=state(db,account,moment)
            answer=_encoded(encode(db,result,after,cash.balance(db,account)));validate()
            cash.record(db,key,account,'native:'+str(kind),hashed,dict(owner=uid,products=result['products'],purchase_id=after['purchase_id'],item_uids=[i['uid']for i in result['items']],item_positions=[[i['group'],i['slot']]for i in result['items']],changed_positions=[p for p,i in result['changed']],created_at=moment),moment)
            db.commit();return answer
        except BaseException:db.rollback();raise
