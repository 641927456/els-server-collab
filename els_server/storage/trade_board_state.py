"""Original-source escrow and atomic sale/purchase/settlement, draft flags closed.

Native ordinary fees/limits and full attributes are retained. Explicit local
policies cover all-level100亿 price cap and purchased seal removal/used-count
preservation. No VIP entitlement or item source is created here.
"""
from pathlib import Path
from contextlib import closing,contextmanager
import json,sqlite3,time,math
from els_server.domain.trade_board_authority import TradeBoardAuthority
from els_server.domain.inventory_items import validate_item,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol import trade_board_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import insert,remove,next_uid,uid_in_use
from els_server.storage.black_market_state import balance,change_ed
from els_server.storage.game_mail import _active_owner

WRITER_ENABLED=True
SALE_ENABLED=True
POLICY='native-trade-board-escrow-v1'
TABLE='trade_board_listings'
RECEIPTS='trade_board_purchases'
ACTIONS='trade_board_actions'
LISTING_COLUMNS=['id','seller_account_id','seller_uid','item_uid','template','item_json','original_count','remaining','sold_count','returned_count','unit_price','created_at','expires_at','last_moment','gross_ed','claimed_gross_ed','claimed_sold_count','state','generation','policy']
clock=lambda:int(time.time())
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'))

def exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone()is not None

def _listing_schema(db):
 columns=[r[1]for r in db.execute('PRAGMA table_info(trade_board_listings)')]
 if columns!=LISTING_COLUMNS:raise ValueError('TradeBoard unknown saved listing schema')
 return columns

def ensure(db):
 """Only a future qualified original sale writer may establish this lazy schema."""
 if not db.in_transaction:raise ValueError('TradeBoard requires original transaction')
 db.execute('''CREATE TABLE IF NOT EXISTS trade_board_listings(
 id INTEGER PRIMARY KEY AUTOINCREMENT,seller_account_id INTEGER NOT NULL,seller_uid INTEGER NOT NULL,
 item_uid INTEGER NOT NULL,template INTEGER NOT NULL,item_json TEXT NOT NULL,original_count INTEGER NOT NULL,
 remaining INTEGER NOT NULL,sold_count INTEGER NOT NULL DEFAULT 0,returned_count INTEGER NOT NULL DEFAULT 0,
 unit_price INTEGER NOT NULL,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,last_moment INTEGER NOT NULL,
 gross_ed INTEGER NOT NULL DEFAULT 0,claimed_gross_ed INTEGER NOT NULL DEFAULT 0,claimed_sold_count INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL,generation INTEGER NOT NULL DEFAULT 0,policy TEXT NOT NULL)''')
 db.execute('''CREATE UNIQUE INDEX IF NOT EXISTS trade_board_held_item_uid
 ON trade_board_listings(item_uid)WHERE remaining>0''')
 db.execute('''CREATE TABLE IF NOT EXISTS trade_board_purchases(
 operation TEXT PRIMARY KEY,buyer_account_id INTEGER NOT NULL,buyer_uid INTEGER NOT NULL,
 listing_id INTEGER NOT NULL,quantity INTEGER NOT NULL,gross_ed INTEGER NOT NULL,
 source_item_uid INTEGER NOT NULL,digest TEXT NOT NULL,purchased_at INTEGER NOT NULL,policy TEXT NOT NULL)''')
 db.execute('''CREATE TABLE IF NOT EXISTS trade_board_actions(
 operation TEXT PRIMARY KEY,kind INTEGER NOT NULL,account_id INTEGER NOT NULL,owner INTEGER NOT NULL,
 listing_id INTEGER NOT NULL,digest TEXT NOT NULL,source_uid INTEGER NOT NULL,
 quantity INTEGER NOT NULL,gross_ed INTEGER NOT NULL,commission INTEGER NOT NULL,
 settled_units INTEGER NOT NULL,claimed_before INTEGER NOT NULL,policy TEXT NOT NULL)''')
 db.execute('CREATE UNIQUE INDEX IF NOT EXISTS trade_board_original_sale ON trade_board_actions(listing_id)WHERE kind=2564')

def _sale_origin(db,r,item):
 """A table/policy string alone is never an authenticated listing producer."""
 if not exists(db,ACTIONS)or not exists(db,'inventory_action_receipts'):raise ValueError('TradeBoard has no paired original sale producer')
 rows=db.execute('''SELECT a.operation,a.account_id,a.owner,a.digest,a.source_uid,a.quantity,a.gross_ed,a.commission,a.policy,
  i.owner,i.kind,i.request_hash,i.before_json FROM trade_board_actions a LEFT JOIN inventory_action_receipts i ON i.operation_id=a.operation
  WHERE a.kind=2564 AND a.listing_id=?''',(r['id'],)).fetchall()
 if len(rows)!=1:raise ValueError('TradeBoard exact unique original sale producer')
 a=rows[0]
 if(a[1:3]!=(r['seller_account_id'],r['seller_uid'])or a[5:9]!=(r['original_count'],1000,0,POLICY)
    or a[9:12]!=(r['seller_uid'],0xa04,a[3])):raise ValueError('TradeBoard original sale receipt pairing')
 before=json.loads(a[12])
 if type(before)is not list or any(type(i)is not dict or type(i.get('uid'))is not int for i in before):raise ValueError('TradeBoard original source receipt array')
 sources=[validate_item(i)for i in before if i['uid']==a[4]]
 if len(sources)!=1:raise ValueError('TradeBoard original seller source UID')
 source=sources[0]
 if source['template']!=r['template']or source['count']<r['original_count']:raise ValueError('TradeBoard original source quantity/template')
 expected=dict(source,uid=r['item_uid'],count=r['original_count'])
 if item.get('sealed',False)and not source.get('sealed',False):expected.update(sealed=True,seal_used=source.get('seal_used',0)+1)
 if expected!=item:raise ValueError('TradeBoard escrow differs from full original source attributes')

def listing(db,identity):
 keys=_listing_schema(db)
 row=db.execute('SELECT * FROM trade_board_listings WHERE id=?',(identity,)).fetchone()
 if row is None:return None
 r=dict(zip(keys,row))
 integers=('id','seller_account_id','seller_uid','item_uid','template','original_count','remaining','sold_count','returned_count','unit_price','created_at','expires_at','last_moment','gross_ed','claimed_gross_ed','claimed_sold_count','generation')
 if any(type(r[k])is not int or not 0<=r[k]<2**63 for k in integers)or type(r['item_json'])is not str:raise ValueError('TradeBoard saved scalar/source type')
 item=validate_item(json.loads(r['item_json']))
 if(r['policy']!=POLICY or type(r['id'])is not int or not 0<r['id']<2**63
    or(item['uid'],item['template'],item['count'])!=(r['item_uid'],r['template'],r['original_count'])
    or item['group']!=TEMPLATE_BAG_GROUPS[item['template']]
    or any(type(r[k])is not int or r[k]<0 for k in('original_count','remaining','sold_count','returned_count','gross_ed','claimed_gross_ed','generation'))
    or r['original_count']!=r['remaining']+r['sold_count']+r['returned_count']
    or not 1<=r['unit_price']<=10_000_000_000
    or r['gross_ed']!=r['unit_price']*r['sold_count']or not r['claimed_gross_ed']<=r['gross_ed']<2**63
    or not 0<=r['claimed_sold_count']<=r['sold_count']or r['claimed_gross_ed']!=r['unit_price']*r['claimed_sold_count']
    or not 0<=r['created_at']<r['expires_at']<2**40 or not r['created_at']<=r['last_moment']<2**40
    or r['state']not in('active','sold','expired','cancelled','returned','settling','claimed')):raise ValueError('TradeBoard exact saved listing')
 if(r['state']=='active'and not r['remaining']or r['state']=='sold'and r['remaining']
    or r['state']=='claimed'and(r['remaining']or r['gross_ed']!=r['claimed_gross_ed'])
    or r['state']=='settling'and(r['remaining']or r['claimed_sold_count']>=r['sold_count'])
    or r['state']in('active','sold')and r['claimed_sold_count']):raise ValueError('TradeBoard inconsistent saved phase')
 _active_owner(db,r['seller_account_id'],r['seller_uid']);_sale_origin(db,r,item);r['item']=item
 return r

def read_offers(db,now):
 if(not db.in_transaction or db.execute('PRAGMA query_only').fetchone()!=(1,)
    or type(now)is not int or not 0<=now<2**40):raise ValueError('TradeBoard original readonly snapshot')
 if not exists(db,TABLE):return []
 _listing_schema(db)
 result=[]
 for(identity,)in db.execute("SELECT id FROM trade_board_listings WHERE state='active'AND remaining>0 AND expires_at>?ORDER BY id",(now,)).fetchall():
  r=listing(db,identity);item=dict(r['item'],count=r['remaining'])
  if r['last_moment']>now:raise ValueError('TradeBoard future active source')
  if item.get('expires_at',now+1)<=now:continue
  name=db.execute('SELECT name FROM characters WHERE uid=?',(r['seller_uid'],)).fetchone()
  if name is None:raise ValueError('TradeBoard seller identity missing')
  result.append(dict(listing_id=identity,seller_char_uid=r['seller_uid'],seller_account_id=r['seller_account_id'],seller_name=name[0],expires_at=r['expires_at'],unit_price=r['unit_price'],item=item))
 return result

def own_rows(db,owner,now):
 if not db.in_transaction:raise ValueError('TradeBoard own rows require actual transaction')
 if not exists(db,TABLE):return []
 _listing_schema(db)
 result=[]
 for(identity,)in db.execute("SELECT id FROM trade_board_listings WHERE seller_uid=?AND state!='claimed'ORDER BY id",(owner,)).fetchall():
  r=listing(db,identity)
  if r['last_moment']>now:raise ValueError('TradeBoard future own listing')
  r['seller_name']=db.execute('SELECT name FROM characters WHERE uid=?',(owner,)).fetchone()[0]
  r['view_state']=1 if r['state']=='active'and r['expires_at']>now and r['remaining']else 2
  # Native own-list +59 is outstanding sold quantity. After partial pickup
  # its unit-price/5% display exactly matches the still escrowed net amount.
  r['total_sold_count']=r['sold_count'];r['sold_count']-=r['claimed_sold_count']
  r['vip_type']=1;result.append(r)
 return result

def require_deletion_unlocked(db,owner):
 if exists(db,TABLE)and db.execute("SELECT 1 FROM trade_board_listings WHERE seller_uid=?AND(state!='claimed'OR remaining>0 OR gross_ed!=claimed_gross_ed)LIMIT 1",(owner,)).fetchone():
  from els_server.storage.character_lifecycle import LifecycleError
  raise LifecycleError('Character has an original unclaimed TradeBoard listing')

def _authority(db,authority,path,owner,account_id,kind,now):
 if(type(authority)is not TradeBoardAuthority or(authority.path,authority.owner,authority.account_id)!=(path,owner,account_id)
    or authority.kind!=kind):raise ValueError('TradeBoard captured original authority required')
 if db.execute('PRAGMA database_list').fetchall()!=[(0,'main',str(path))]:raise ValueError('TradeBoard original SQL root')
 authority.check(db,now);_active_owner(db,account_id,owner)

@contextmanager
def _transaction(path,owner,kind,payload,operation,account_id,authority):
 owner,digest=_identity(owner,kind,payload,operation);path=Path(path).resolve()
 with closing(sqlite3.connect(path,timeout=15))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=clock()
  _authority(db,authority,path,owner,account_id,kind,now)
  before=load_items(db,owner);old=_previous(db,operation,digest)
  paired=db.execute('SELECT kind,account_id,owner,listing_id,digest,source_uid,quantity,gross_ed,commission,policy FROM trade_board_actions WHERE operation=?',(operation,)).fetchone()if exists(db,ACTIONS)else None
  if(old is None)!=(paired is None):raise ValueError('TradeBoard unpaired original action history')
  if paired is not None and(paired[:3]!=(kind,account_id,owner)or paired[4]!=digest or paired[9]!=POLICY):raise ValueError('TradeBoard exact action history')
  yield db,now,digest,before,old,paired

def _commit_action(db,operation,digest,owner,account,kind,r,source_uid,quantity,gross,commission,points,before,after,result,*,settled_units=0,claimed_before=0):
 encode_event(result)
 db.execute('INSERT INTO trade_board_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(operation,kind,account,owner,r['id'],digest,source_uid,quantity,gross,commission,settled_units,claimed_before,POLICY))
 _commit(db,operation,digest,owner,kind,points,before,after)
 return[result]

def _normal_sale_item(db,owner,item,count,aux_uid,before,now):
 from els_server.game_data import client_data
 from els_server.domain.cartridge_registration_rules import require_unbound
 if item is None or item['group']not in(1,2,3,4,5,6,7,27)or not 0<count<=item['count']:raise ValueError('TradeBoard exact original owned bag item')
 require_current(item,now=now);require_unlocked(item,now=now);require_unbound(db,item['uid'])
 raw=client_data().item(item['template'])['record'];flags=int.from_bytes(raw[4:8],'little');typ=(raw[8]>>3)&31
 if flags&32:raise ValueError('TradeBoard original item forbids trade')
 if 'expires_at'in item or item.get('identified')is False or item.get('wardrobe_hanger',False):raise ValueError('TradeBoard original timed/unidentified/hanger item refused')
 if typ in(1,2)and not flags&1 and item.get('durability',0)!=int.from_bytes(raw[0xc8:0xca],'little',signed=True):raise ValueError('TradeBoard damaged equipment')
 points=[(item['group'],item['slot'])]
 if item.get('sealed',False):
  if aux_uid or item.get('seal_used',0)>99:raise ValueError('TradeBoard unsupported seal history or extra stamp')
 elif flags&2:
  from els_server.storage.item_seals import _target,assign
  from els_server.domain.item_sealing_rules import accepts
  raw=_target(item,sealing=True);maximum=raw[0xd7];used=item.get('seal_used',0)
  if count!=1 or not 1<=maximum<=99 or used>=maximum:raise ValueError('TradeBoard original sealing allowance exhausted')
  stamp=next((i for i in before if i['uid']==aux_uid),None)
  if(stamp is None or stamp['group']!=4 or not accepts(stamp['template'],raw)
     or stamp.get('sealed',False)or stamp.get('seal_used',0)):raise ValueError('TradeBoard exact matching original stamp')
  require_current(stamp,now=now);require_unlocked(stamp,now=now)
  assign(db,owner,item['uid'],True,used+1)
  if stamp['count']>1:
   if db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=?AND owner=?AND count=?',(stamp['uid'],owner,stamp['count'])).rowcount!=1:raise ValueError('TradeBoard stamp source changed')
  else:remove(db,owner,stamp)
  points.append((stamp['group'],stamp['slot']));item=dict(item,sealed=True,seal_used=used+1)
 elif aux_uid:raise ValueError('TradeBoard extra stamp on a directly tradeable item')
 return item,points

def _source_price_limit(db,owner):
 # Explicit user rule: all supported levels1..99 use100亿 unit-price cap.
 # This is not a claim about the missing official lower-level price table.
 row=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
 if row is None or type(row[0])is not int or not 1<=row[0]<=99:raise ValueError('TradeBoard actual source level')
 return 10_000_000_000

def _new_uid(db):
 identity=next_uid(db)
 if uid_in_use(db,identity)or(exists(db,TABLE)and db.execute('SELECT 1 FROM trade_board_listings WHERE item_uid=?AND remaining>0',(identity,)).fetchone()):raise ValueError('TradeBoard allocated UID already live or held')
 return identity

def perform_sale(path,owner,payload,operation,*,account_id,authority):
 uid,template,count,price,aux_uid=wire.sale_request(payload)
 with _transaction(path,owner,0xa04,payload,operation,account_id,authority)as(db,now,digest,before,old,paired):
  if old is not None:
   r=listing(db,paired[3])
   if r is None or(paired[5],paired[6])!=(uid,count)or r['template']!=template or r['unit_price']!=price:raise ValueError('TradeBoard original sale source missing')
   result=wire.sale_ack(balance(db,owner)[0],current_changes(db,operation,owner,0xa04,old,before),own_rows(db,owner,now));encode_event(result);return[result]
  if not SALE_ENABLED:raise ValueError('TradeBoard unqualified sale source')
  if price>_source_price_limit(db,owner):raise ValueError('TradeBoard original source price bound')
  original=next((i for i in before if i['uid']==uid),None)
  if original is None or original['template']!=template:raise ValueError('TradeBoard actual source template')
  item,points=_normal_sale_item(db,owner,original,count,aux_uid,before,now)
  if item['template']!=template:raise ValueError('TradeBoard actual source template')
  rows=own_rows(db,owner,now)
  if len(rows)>=10:raise ValueError('TradeBoard original ordinary ten listing slots')
  if balance(db,owner)[0]<1000:raise ValueError('TradeBoard original registration fee unavailable')
  ensure(db)
  if count==item['count']:escrow=dict(item);remove(db,owner,item)
  else:
   escrow=dict(item,uid=_new_uid(db),count=count)
   if db.execute('UPDATE inventory_items SET count=count-?WHERE uid=?AND owner=?AND count=?',(count,uid,owner,item['count'])).rowcount!=1:raise ValueError('TradeBoard original source changed')
  if uid_in_use(db,escrow['uid']):raise ValueError('TradeBoard source remained live after escrow')
  identity=db.execute('''INSERT INTO trade_board_listings(seller_account_id,seller_uid,item_uid,template,item_json,original_count,remaining,unit_price,created_at,expires_at,last_moment,state,policy)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(account_id,owner,escrow['uid'],template,canonical(escrow),count,count,price,now,now+86400,now,'active',POLICY)).lastrowid
  ed,_=change_ed(db,owner,-1000);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  # Both durable original receipts exist before any own-list encoder reads
  # the new row; all remain in this same uncommitted transaction.
  db.execute('INSERT INTO trade_board_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(operation,0xa04,account_id,owner,identity,digest,uid,count,1000,0,0,0,POLICY))
  _commit(db,operation,digest,owner,0xa04,points,before,after)
  result=wire.sale_ack(ed,[(point,current.get(point))for point in points],own_rows(db,owner,now))
  encode_event(result);return[result]

def perform_cancel(path,owner,payload,operation,*,account_id,authority):
 identity=wire.cancel_request(payload)
 with _transaction(path,owner,0x9fc,payload,operation,account_id,authority)as(db,now,digest,before,old,paired):
  r=listing(db,identity)if exists(db,TABLE)else None
  if r is None or(r['seller_uid'],r['seller_account_id'])!=(owner,account_id):raise ValueError('TradeBoard cancel actual seller')
  if old is not None:
   if paired[3]!=identity:raise ValueError('TradeBoard cancel original listing')
   result=wire.cancel_ack(identity,own_rows(db,owner,now));encode_event(result);return[result]
  # Closing new-sale/purchase flags must not strand already escrowed goods.
  if not r['last_moment']<=now<r['expires_at']or r['state']!='active'or not r['remaining']:raise ValueError('TradeBoard cancel actual active listing')
  if db.execute("UPDATE trade_board_listings SET state='cancelled',generation=generation+1,last_moment=?WHERE id=?AND generation=?",(now,identity,r['generation'])).rowcount!=1:raise ValueError('TradeBoard cancel generation')
  result=wire.cancel_ack(identity,own_rows(db,owner,now))
  return _commit_action(db,operation,digest,owner,account_id,0x9fc,r,r['item_uid'],0,0,0,[],before,before,result)

def commission(gross):
 if type(gross)is not int or not 0<=gross<2**63:raise ValueError('TradeBoard native fee base')
 return math.floor(float(gross)*0.05+0.5)

def settlement_batch(pending,price,available):
 """Largest whole-unit batch fitting the actual current wallet, no ED clipping.

 Fee differences telescope to the original native whole fee. The remainder
 has exactly the fee displayed by the original native own-list consumer.
 """
 if(type(pending)is not int or not 0<=pending<2**31 or type(price)is not int or not 1<=price<=10_000_000_000
    or type(available)is not int or not 0<=available<=70_000_000_000):raise ValueError('TradeBoard actual settlement bound')
 old_fee=commission(pending*price)
 def values(units):
  gross=units*price;fee=old_fee-commission((pending-units)*price);return gross,fee,gross-fee
 lo,hi=0,pending
 while lo<hi:
  mid=(lo+hi+1)//2
  if values(mid)[2]<=available:lo=mid
  else:hi=mid-1
 return(lo,*values(lo))

def settlement_receipts(db,r):
 """Verify all original pickup intervals before paying any further units."""
 if not db.in_transaction:raise ValueError('TradeBoard original settlement transaction')
 rows=db.execute('''SELECT a.operation,a.account_id,a.owner,a.digest,a.source_uid,a.quantity,a.gross_ed,a.commission,
   a.settled_units,a.claimed_before,a.policy,i.owner,i.kind,i.request_hash
   FROM trade_board_actions a LEFT JOIN inventory_action_receipts i ON i.operation_id=a.operation
   WHERE a.kind=?AND a.listing_id=?''',(0xa06,r['id'])).fetchall()
 returned=gross=fees=units=0;intervals=[];result=[]
 for a in rows:
  if(a[1:3]!=(r['seller_account_id'],r['seller_uid'])or a[4]!=r['item_uid']or a[10]!=POLICY
     or a[11:14]!=(r['seller_uid'],0xa06,a[3])or any(type(a[k])is not int or a[k]<0 for k in(5,6,7,8,9))
     or a[9]+a[8]>r['sold_count']or a[6]!=r['unit_price']*a[8]
     or a[7]!=commission((r['sold_count']-a[9])*r['unit_price'])-commission((r['sold_count']-a[9]-a[8])*r['unit_price'])
     or not(a[5]or a[8])or(a[5]and a[9])):raise ValueError('TradeBoard original partial settlement receipt')
  if a[8]:intervals.append((a[9],a[9]+a[8]))
  returned+=a[5];gross+=a[6];fees+=a[7];units+=a[8]
  result.append(dict(operation=a[0],returned_count=a[5],gross_ed=a[6],commission=a[7],settled_units=a[8],claimed_before=a[9]))
 end=0
 for first,last in sorted(intervals):
  if first!=end:raise ValueError('TradeBoard duplicate or missing settlement interval')
  end=last
 if(returned,gross,units,end)!=(r['returned_count'],r['claimed_gross_ed'],r['claimed_sold_count'],r['claimed_sold_count'])or fees!=commission(r['gross_ed'])-commission(r['gross_ed']-r['claimed_gross_ed']):raise ValueError('TradeBoard outstanding settlement ledger mismatch')
 return result

def perform_pickup(path,owner,payload,operation,*,account_id,authority):
 identity,resell=wire.pickup_request(payload)
 with _transaction(path,owner,0xa06,payload,operation,account_id,authority)as(db,now,digest,before,old,paired):
  r=listing(db,identity)if exists(db,TABLE)else None
  if r is None or(r['seller_uid'],r['seller_account_id'])!=(owner,account_id):raise ValueError('TradeBoard pickup actual seller')
  settlement_receipts(db,r)
  if old is not None:
   if paired[3]!=identity or paired[5]!=r['item_uid']:raise ValueError('TradeBoard pickup original listing')
   # Resell is an opening action; replay must not reopen a stale registration
   # source after returned items moved, were consumed, or were listed again.
   result=wire.pickup_ack(identity,balance(db,owner)[0],current_changes(db,operation,owner,0xa06,old,before),own_rows(db,owner,now),False);encode_event(result);return[result]
  # Existing real escrow settlement remains available during compatible
  # recovery, even when both new production flags are closed.
  if r['last_moment']>now or r['state']=='claimed'or(r['state']=='active'and now<r['expires_at']):raise ValueError('TradeBoard pickup actual ended listing')
  if resell and not r['remaining']:raise ValueError('TradeBoard resell has no original remaining items')
  from els_server.domain.bank_rules import player_ed_limit
  level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
  available=max(0,player_ed_limit(level)-balance(db,owner)[0]);pending=r['sold_count']-r['claimed_sold_count']
  units,gross,fee,net=settlement_batch(pending,r['unit_price'],available)
  if not r['remaining']and not units:raise ValueError('TradeBoard actual seller ED capacity')
  quantity=r['remaining'];points=_place(db,owner,r['item'],quantity,True,before)if quantity else[]
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};ed=change_ed(db,owner,net)[0]if net else balance(db,owner)[0]
  phase='claimed'if units==pending else'settling'
  if db.execute('''UPDATE trade_board_listings SET remaining=0,returned_count=returned_count+?,
    claimed_gross_ed=claimed_gross_ed+?,claimed_sold_count=claimed_sold_count+?,state=?,last_moment=?,generation=generation+1
    WHERE id=?AND generation=?''',(quantity,gross,units,phase,now,identity,r['generation'])).rowcount!=1:raise ValueError('TradeBoard pickup original generation')
  result=wire.pickup_ack(identity,ed,[(p,current.get(p))for p in points],own_rows(db,owner,now),resell)
  return _commit_action(db,operation,digest,owner,account_id,0xa06,r,r['item_uid'],quantity,gross,fee,points,before,after,result,settled_units=units,claimed_before=r['claimed_sold_count'])

def _place(db,owner,item,quantity,all_remaining,before):
 if uid_in_use(db,item['uid']):raise ValueError('TradeBoard escrow UID already in a live container')
 group=TEMPLATE_BAG_GROUPS[item['template']];maximum=TEMPLATE_MAX_STACKS[item['template']]
 if not 0<quantity<=maximum:raise ValueError('TradeBoard native item stack bound')
 signature=lambda i:{k:v for k,v in i.items()if k not in('uid','count','group','slot')}
 remaining=quantity;positions=[]
 for target in before:
  if remaining and maximum>1 and target['group']==group and signature(target)==signature(item):
   add=min(remaining,maximum-target['count'])
   if add:
    if db.execute('UPDATE inventory_items SET count=count+?WHERE uid=?AND owner=?AND count=?',(add,target['uid'],owner,target['count'])).rowcount!=1:raise ValueError('TradeBoard merge changed')
    remaining-=add;positions.append((group,target['slot']))
 if remaining:
  from els_server.storage.bag_capacity import allowances
  occupied={i['slot']for i in before if i['group']==group};limit=allowances(db,owner)[group]
  slot=next((n for n in range(limit)if n not in occupied),None)
  if slot is None:raise ValueError('TradeBoard full original bag')
  bought=dict(item,uid=item['uid']if all_remaining else _new_uid(db),count=remaining,group=group,slot=slot)
  insert(db,owner,bought);positions.append((group,slot))
 return positions

def perform_purchase(path,owner,payload,operation,*,account_id,authority):
 owner,digest=_identity(owner,0xa08,payload,operation);path=Path(path).resolve();candidates=wire.purchase_candidates(payload)
 if(type(authority)is not TradeBoardAuthority or(authority.path,authority.owner,authority.account_id)!=(path,owner,account_id)):raise ValueError('TradeBoard captured original authority required')
 with closing(sqlite3.connect(path,timeout=15))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=clock()
  _authority(db,authority,path,owner,account_id,0xa08,now)
  before=load_items(db,owner);old=_previous(db,operation,digest)
  paired=db.execute('SELECT buyer_account_id,buyer_uid,listing_id,quantity,gross_ed,source_item_uid,digest,policy,purchased_at FROM trade_board_purchases WHERE operation=?',(operation,)).fetchone()if exists(db,RECEIPTS)else None
  if old is not None:
   if(paired is None or paired[:2]!=(account_id,owner)or paired[6:8]!=(digest,POLICY)
      or not any(identity==paired[2]and quantity==paired[3]for identity,template,quantity in candidates)):raise ValueError('TradeBoard exact paired purchase history')
   r=listing(db,paired[2])
   if(r is None or not 0<paired[3]<=r['original_count']or paired[4]!=paired[3]*r['unit_price']
      or paired[5]!=r['item_uid']or type(paired[8])is not int
      or not r['created_at']<=paired[8]<r['expires_at']or paired[8]>now):raise ValueError('TradeBoard original purchase source ledger missing')
   remaining=r['remaining']
   result=wire.purchase_ack(balance(db,owner)[0],current_changes(db,operation,owner,0xa08,old,before),paired[2],remaining);encode_event(result);return[result]
  if paired is not None:raise ValueError('TradeBoard orphan purchase history')
  if not WRITER_ENABLED:raise ValueError('TradeBoard purchase writer not qualified')
  if not exists(db,TABLE)or not exists(db,RECEIPTS):raise ValueError('TradeBoard has no qualified listing producer')
  matches=[]
  for identity,template,quantity in candidates:
   r=listing(db,identity)
   if(r and r['template']==template and r['state']=='active'and 0<quantity<=r['remaining']):matches.append((r,quantity))
  if len(matches)!=1:raise ValueError('TradeBoard absent or ambiguous real listing')
  r,quantity=matches[0]
  if r['seller_uid']==owner or not r['last_moment']<=now<r['expires_at']:raise ValueError('TradeBoard own/expired/future listing')
  item=r['item'];require_current(item,now=now);require_unlocked(item,now=now)
  gross=r['unit_price']*quantity
  if not 0<gross<=balance(db,owner)[0]:raise ValueError('TradeBoard actual ED unavailable')
  if r['gross_ed']+gross>=2**63:raise ValueError('TradeBoard original signed ledger capacity')
  delivered=item
  if item.get('sealed',False):
   if item.get('seal_used',0)>99:raise ValueError('TradeBoard unencodable unsealed history')
   # Explicit user-authorized local policy; no stamp/uses are refunded.
   delivered=dict(item,sealed=False,seal_used=item.get('seal_used',0))
  points=_place(db,owner,delivered,quantity,quantity==r['remaining'],before);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  ed,_=change_ed(db,owner,-gross)
  remaining=r['remaining']-quantity
  if db.execute('''UPDATE trade_board_listings SET remaining=?,sold_count=sold_count+?,gross_ed=gross_ed+?,
    state=?,last_moment=?,generation=generation+1 WHERE id=?AND generation=?AND remaining=?AND gross_ed=?''',
    (remaining,quantity,gross,'active'if remaining else'sold',now,r['id'],r['generation'],r['remaining'],r['gross_ed'])).rowcount!=1:raise ValueError('TradeBoard listing changed')
  db.execute('INSERT INTO trade_board_purchases VALUES(?,?,?,?,?,?,?,?,?,?)',(operation,account_id,owner,r['id'],quantity,gross,item['uid'],digest,now,POLICY))
  result=wire.purchase_ack(ed,[(p,current.get(p))for p in points],r['id'],remaining);encode_event(result)
  _commit(db,operation,digest,owner,0xa08,points,before,after)
  return[result]
