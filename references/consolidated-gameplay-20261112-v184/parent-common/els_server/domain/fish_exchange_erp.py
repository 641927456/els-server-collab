"""Only the five original House40256 fish recipes mint their eleven ERP outputs.

The legacy existing-owned potion reader remains strict. New factory objects
carry a separate live transaction provenance and never masquerade as reads.
"""
import hashlib,json,sqlite3,struct
from collections import Counter
from pathlib import Path

IDS=frozenset(range(136161,136172))
# Exact current sourcequantity andoriginalresult rows, never a genericERPgrant.
PROFILES={
 (135937,3,136161):(10,((136161,1,20),)),
 (135936,2,0):(10,((136162,1,37),(136163,1,33),(136164,1,30))),
 (135935,2,0):(10,((136165,1,37),(136166,1,33),(136167,1,30))),
 (135934,2,0):(10,((136168,1,37),(136169,1,33),(136170,1,30))),
 (135933,1,0):(1,((136171,1,100),)),
}


def supports(request):
    key=(request.source,request.exchange_type,request.destination)
    return key in PROFILES and request.source_quantity==PROFILES[key][0]
_TOKEN=object()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


class _IssuedPotion(dict):
    __slots__=('_source','_original')


def _shape(item):
    keys={'uid','template','metadata','count','group','slot'}
    if (type(item)is not dict or set(item)-{'lock_until','sealed','seal_used'}!=keys
            or any(type(item[k])is not int for k in keys)
            or not 0<item['uid']<2**63 or item['template']not in IDS
            or (item['metadata'],item['group'])!=(2,4)or not 1<=item['count']<=500):
        raise ValueError('Finite fish ERP factory item shape')
    from els_server.domain.bag_capacity import wire_limit
    from els_server.domain.item_locks import require_unlocked
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Fish ERP original bag slot')
    require_unlocked(item)
    if item.get('sealed',False):raise ValueError('Fish ERP sealed destination')
    return item


def validate_issued(item):
    if type(item)is not _IssuedPotion or dict(item)!=item._original:
        raise ValueError('Fish ERP unchanged issued factory object required')
    source=validate_source(item._source);source.current()
    if source.instances.get(item['uid'])!=item._original:
        raise ValueError('Fish ERP unminted instance identity')
    _shape(dict(item))
    return item


class _Source:
    def __init__(self,token,db,owner,account,payload,operation,before,guard):
        if token is not _TOKEN:raise ValueError('Fish ERP finite source constructor')
        from els_server.protocol.fish_exchange_messages import request
        from els_server.domain.fish_exchange_rules import recipe
        from els_server.domain.erp_potions_existing import definitions
        from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
        from els_server.storage.inventory_actions import _identity
        from els_server.game_data import client_data
        r=request(payload);rows=recipe(r)
        if r.house!=40256 or not supports(r):raise ValueError('Fish ERP exact original recipe source')
        profile=PROFILES[(r.source,r.exchange_type,r.destination)]
        if {(x['destination'],x['quantity'],x['rate'])for x in rows}!=set(profile[1]):
            raise ValueError('Fish ERP original recipe fields')
        verified=definitions()
        if any(struct.unpack_from('<I',client_data().item(t)['record'],0x10)[0]!=500 or TEMPLATE_MAX_STACKS[t]!=500 or hashlib.sha256(client_data().item(t)['record']).hexdigest()!=verified[t]['record_sha256'] for t in IDS):
            raise ValueError('Fish ERP original native500 stack')
        self.db=db;self.owner=owner;self.account=account;self.payload=bytes(payload)
        self.operation=operation;self.guard=guard;self.rows=rows;self.request=r
        self.digest=_identity(owner,0x223,b'House40256:'+payload,operation)[1]
        self.before=json.loads(canonical(before));self.rolls=[];self.awards=Counter()
        self.instances={};self.bound=False;self.plan=None
        self.current()
        from els_server.storage.inventory_state import load_items
        if canonical(load_items(db,owner))!=canonical(self.before):
            raise ValueError('Fish ERP source must precede original consumption')

    def current(self):
        if not isinstance(self.db,sqlite3.Connection)or not self.db.in_transaction or not callable(self.guard):
            raise ValueError('Fish ERP live original SQL writer required')
        attached=self.db.execute('PRAGMA database_list').fetchall()
        if len([r for r in attached if r[1]=='main'and r[2]])!=1 or any(r[1]not in('main','temp')for r in attached):
            raise ValueError('Fish ERP original single database')
        self.guard(self.db)
        from els_server.storage.item_actor import require_active_character
        require_active_character(self.db,self.owner)
        if self.db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.owner,)).fetchone()!=(self.account,):
            raise ValueError('Fish ERP original account owner')

    def draw(self,roll):
        self.current()
        if self.bound or self.request.exchange_type!=2 or type(roll)is not int or not 0<=roll<100 or len(self.rolls)>=self.request.quantity:
            raise ValueError('Fish ERP original draw bound')
        self.rolls.append(roll)
        for row in self.rows:
            roll-=row['rate']
            if roll<0:self.awards[row['destination']]+=row['quantity'];break

    def choose(self,row):
        self.current()
        if (self.bound or self.request.exchange_type not in(1,3)or len(self.rows)!=1
                or row!=self.rows[0]or len(self.rolls)>=self.request.quantity):
            raise ValueError('Fish ERP exact deterministic/selected result')
        self.rolls.append(None);self.awards[row['destination']]+=row['quantity']

    def validate_plan(self,plan):
        self.current()
        actual=Counter()
        for p in plan:
            if (type(p)is not dict or set(p)!={'template','metadata','quantity','group'}
                    or any(type(v)is not int for v in p.values())or p['template']not in IDS
                    or(p['metadata'],p['group'])!=(2,4)or not 1<=p['quantity']<=999):
                raise ValueError('Fish ERP finite factory plan')
            actual[p['template']]+=p['quantity']
        if not plan or len(self.rolls)!=self.request.quantity or actual!=self.awards:
            raise ValueError('Fish ERP plan did not come from original server draws')

    def bind_factory(self,db,owner,plan):
        if self.bound or db is not self.db or owner!=self.owner:
            raise ValueError('Fish ERP factory owner/transaction/reuse mismatch')
        self.validate_plan(plan)
        from els_server.storage.inventory_state import load_items
        after=load_items(db,owner);a={i['uid']:i for i in self.before};b={i['uid']:i for i in after}
        candidates=[i for i in self.before if i['template']==self.request.source and i['group']==21]
        demand=self.request.source_quantity*self.request.quantity
        for item in sorted(candidates,key=lambda i:(i['slot'],i['uid'])):
            if not demand:break
            from els_server.domain.item_locks import require_unlocked
            from els_server.domain.item_expiration import require_current
            try:require_unlocked(item);require_current(item)
            except ValueError:continue
            take=min(demand,item['count']);demand-=take
            if take==item['count']:a.pop(item['uid'])
            else:a[item['uid']]=dict(item,count=item['count']-take)
        if demand or canonical(a)!=canonical(b):raise ValueError('Fish ERP original owned fish debit proof')
        self.consumed=b;self.plan=json.loads(canonical(plan));self.bound=True

    def can_stack(self,item,plan):
        self.current()
        if not self.bound:raise ValueError('Fish ERP unbound factory')
        try:_shape(dict(item))
        except ValueError:return False
        return True

    def admit_instance(self,item):
        self.current()
        if not self.bound:raise ValueError('Fish ERP factory not bound')
        _shape(item)
        # A new UID is the original inventory sequence; an existing one is
        # the same saved owned destination with only its count changed.
        row=self.db.execute('SELECT owner,template,metadata,count,bag_group,slot FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone()
        if row is None:
            if self.db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()!=(item['uid'],):
                raise ValueError('Fish ERP original new UID sequence')
        elif row!=(self.owner,item['template'],2,item['count'],4,item['slot']):
            raise ValueError('Fish ERP existing destination SQL mismatch')
        old=self.consumed.get(item['uid'])
        if old is not None and any(item.get(k)!=old.get(k)for k in set(item)|set(old)if k!='count'):
            raise ValueError('Fish ERP changed existing destination fields')
        result=_IssuedPotion(item);result._source=self;result._original=dict(item)
        self.instances[item['uid']]=dict(item);return result

    def verify_after(self):
        self.current()
        if not self.bound:raise ValueError('Fish ERP unfinished factory')
        from els_server.storage.inventory_state import load_items
        after={i['uid']:dict(i)for i in load_items(self.db,self.owner)}
        before=self.consumed
        for uid,item in before.items():
            now=after.get(uid)
            if item['template']not in IDS:
                if now!=item:raise ValueError('Fish ERP unrelated saved item changed')
            elif now is None or any(now.get(k)!=item.get(k)for k in set(now)|set(item)if k!='count'):
                raise ValueError('Fish ERP original destination identity changed')
        if any(i['template']not in IDS for uid,i in after.items()if uid not in before):
            raise ValueError('Fish ERP unrelated new grant')
        delta=Counter()
        for item in after.values():
            if item['template']in IDS:delta[item['template']]+=item['count']
        for item in before.values():
            if item['template']in IDS:delta[item['template']]-=item['count']
        if +delta!=self.awards or any(n<0 for n in delta.values()):
            raise ValueError('Fish ERP saved awards do not match original draws')


def validate_source(source):
    if type(source)is not _Source:raise ValueError('Original finite fish ERP source required')
    return source


def begin(db,owner,account,payload,operation,before,guard):
    return _Source(_TOKEN,db,owner,account,payload,operation,before,guard)
