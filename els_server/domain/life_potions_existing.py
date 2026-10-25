"""Four current registered life potions; original owned219 and life8B3 only."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType
TEMPLATES=(135952,135953,135954,135955)
PAYLOAD_SHA='0630a9c7ea3fe7b768dc7b855c2352b03367e96451cc3f6e153b1b2ec3fa6c25'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/life_potions_existing.json').read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or d['client_sha256']!=CLIENT_SHA or tuple(r['template']for r in d['rows'])!=TEMPLATES:
        raise ValueError('Life potion current source binding')
    for r in d['rows']:
        item=client_data().item(r['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']or item['record'].hex()!=r['record_hex']
            or(item['item_type'],item['metadata'],item['flags8'])!=(7,2,56)or struct.unpack_from('<I',item['record'],16)[0]!=300
            or r['restore']!=1440 or r['minimum_level']!=99):raise ValueError('Life potion exact record/restore')
    return MappingProxyType({r['template']:MappingProxyType(r)for r in d['rows']})

def admitted():return frozenset(t for t,r in definitions().items()if r.get('admitted',True))

class _ExistingLifePotion(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    if (type(item)is not dict or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys
        or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63
        or item['template']not in TEMPLATES or(item['metadata'],item['group'])!=(2,4)or not 0<item['count']<=300):
        raise ValueError('Existing life potion SQL shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Life potion bag slot')
    definitions();v=dict(item)
    if 'expires_at'in v:
        from els_server.domain.item_expiration import validate
        v['expires_at']=validate(v['expires_at'])
    if 'lock_until'in v:
        from els_server.domain.item_locks import validate
        v['lock_until']=validate(v['lock_until'])
    if 'sealed'in v or 'seal_used'in v:
        from els_server.storage.item_seals import validate
        validate(v.get('sealed',False),v.get('seal_used',0))
    out=_ExistingLifePotion(v);out._original=dict(v);return out

def validate_existing(item):
    if type(item)is not _ExistingLifePotion or dict(item)!=item._original:raise ValueError('Life potion unchanged SQL reader required')
    read_existing(dict(item));return item

def request(payload):
    if type(payload)is not bytes or len(payload)!=29:raise ValueError('Life potion use width')
    uid,secondary,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or secondary or a or b or n or flag:raise ValueError('Life potion original single-use parameters')
    return uid

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.storage.life_potions_existing import recognizes,perform
    from els_server.domain.equipment_chip_flow import reset_authority
    from els_server.protocol.career_messages import use_ack
    operation=s.shop_session_id+':life-potion:'+str(account.uid)+':'+str(sequence)
    if not recognizes(store.path,account.uid,event.payload,operation):return None
    path=Path(store.path).resolve();root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
    uid=account.uid;aid=account.account_id;shop=s.shop_session_id
    def prepare(db):
        reset_authority(s)
        if (not s.item_test or s.client_build!='dx11_260923'or s.role!='game'or s.phase!='town_ready'
            or not {0x28,0x225,0x227}<=s.completed or type(sequence)is not int or not 0<sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.account is not account or account.store is not store or account.root is not root
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
            or(account.uid,account.account_id,s.shop_session_id)!=(uid,aid,shop)or Path(store.path).resolve()!=path):
            raise ValueError('Life potion current actor/context')
    try:return perform(path,uid,aid,event.payload,operation,prepare=prepare)
    except ValueError:return[use_ack(result=-1)]
