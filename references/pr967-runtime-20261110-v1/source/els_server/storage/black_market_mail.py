"""Original auction escrow into the existing native mailbox/UID consumers."""
import hashlib,json
from els_server.storage import black_market_state as state
from els_server.domain import black_market_rules as rules
def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='black_market_mail'").fetchone())
def meta(db,mid):
 if not exists(db):return None
 return db.execute('SELECT recipient_uid,letter_type FROM black_market_mail WHERE mail_id=?',(mid,)).fetchone()
def issue(db,r,p,lot,kind,ed,now):
 if not db.in_transaction or kind not in('winning','distribution','refund'):raise ValueError('Market original mail writer')
 original=state.round_for(db,r['id']);native=original['lots'][original['index']]
 if(original['revision']!=r['revision']or original['phase']!='bid'or state.canonical(native)!=state.canonical(lot)
    or native['settled']or not native['winner']or native['price']<native['opening']
    or not any(a['uid']==p['uid']and a['account']==p['account']and a['nonce']==p['nonce']for a in original['people'])):raise ValueError('Market exact unsettled lot/recipient source')
 account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(p['uid'],)).fetchone()
 if account!=(p['account'],):raise ValueError('Market saved recipient owner')
 if kind=='winning':
  if p['uid']!=native['winner']or ed!=0 or now<original['deadline']:raise ValueError('Market winning item source')
 elif kind=='refund':
  if p['uid']!=native['winner']or ed!=native['price']or now>=original['deadline']:raise ValueError('Market previous bidder refund source')
 elif(original['local']or p['uid']==native['winner']or now<original['deadline']or ed!=(native['price']*90)//(100*(len(original['people'])-1))):raise ValueError('Market exact native distribution source')
 from els_server.storage.game_mail import ensure
 ensure(db)
 db.execute('''CREATE TABLE IF NOT EXISTS black_market_mail(
 source_key TEXT PRIMARY KEY,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),recipient_uid INTEGER NOT NULL,
 letter_type INTEGER NOT NULL CHECK(letter_type IN(77,78,79)),source_json TEXT NOT NULL)''')
 key=state.canonical([r['id'],native['index'],kind,p['uid'],original['revision']if kind=='refund'else 0])
 source=state.canonical(dict(round=r['id'],revision=r['revision'],lot=native,kind=kind,recipient=p['uid'],account=p['account'],ed=ed))
 previous=db.execute('SELECT mail_id,source_json FROM black_market_mail WHERE source_key=?',(key,)).fetchone()
 if previous:
  if previous[1]!=source:raise ValueError('Market mail retry conflicts')
  return previous[0]
 label={'winning':'中标物品','distribution':'拍卖分红','refund':'竞价返还'}[kind];letter={'winning':77,'distribution':78,'refund':79}[kind]
 body='暗精灵黑市'+label+'。\n本次物品：'+str(native['template'])+' × '+str(native['quantity'])+'\n成交／竞价ED：'+str(native['price'])
 cur=db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)
 VALUES(?,?,?,?,?,?,?,?)''',('black-market-'+hashlib.sha256(key.encode()).hexdigest(),p['account'],'菲塔','暗精灵黑市：'+label,body,ed,now,now+365*86400));mid=cur.lastrowid
 db.execute('INSERT INTO black_market_mail VALUES(?,?,?,?,?)',(key,mid,p['uid'],letter,source))
 if kind=='winning':
  row=next((a for a in rules.definitions()if a['template']==native['template']),None)
  permitted=rules.catalog()['tiers'][str(native['tier'])]['entries']
  if row is None or dict(template=native['template'],quantity=native['quantity'])not in permitted:raise ValueError('Market finite current reward')
  from els_server.storage.item_instances import next_uid
  from els_server.domain.inventory_items import validate_item,item_body
  from els_server.storage.mail_attachments import put
  # Every current outcome is a plain native IT_MATERIAL/IT_SPECIAL instance.
  # Real sequence and original item serializer precede durable escrow; this
  # source has no generic grant path and never needs recipient bag capacity.
  item=validate_item(dict(uid=next_uid(db),template=row['template'],metadata=row['metadata'],group=row['group'],slot=0,count=native['quantity']))
  item_body(item);put(db,mid,item,item)
 # Pre-encode every fresh mailbox projection before the outer writer commits.
 from els_server.storage.player_mail import decorate
 from els_server.protocol.mail_attachment_messages import header,detail
 raw=db.execute('SELECT * FROM game_mail WHERE id=?',(mid,));names=[a[0]for a in raw.description];value=dict(zip(names,raw.fetchone()))
 value=decorate(db,value,now=now);header(value);detail(value)
 return mid
