"""Four retained single-use ordinary EXP potions; no new acquisition source."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType
TEMPLATES=(100005719,100005720,100005721,100005722)
PAYLOAD_SHA='48b25c75362197366de02d6c38d1afe3d7150b32194a099be5678cf4b4186a5e'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/wisdom_potions.json').read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or d['client_sha256']!=CLIENT_SHA or tuple(r['template']for r in d['rows'])!=TEMPLATES or d['new_sources']:
        raise ValueError('Wisdom potion source identity')
    for r,percent in zip(d['rows'],(10,20,50,100)):
        item=client_data().item(r['template']);record=item['record']
        if hashlib.sha256(record).hexdigest()!=r['record_sha256']or record.hex()!=r['record_hex']or(item['item_type'],item['metadata'],item['flags8'])!=(7,0,56)or struct.unpack_from('<I',record,16)[0]!=0 or r['percent']!=percent:
            raise ValueError('Wisdom potion original retained item')
    return MappingProxyType({r['template']:MappingProxyType(r)for r in d['rows']})

def admitted():return frozenset(t for t,r in definitions().items()if r.get('admitted',True))

class _ExistingWisdom(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    if type(item)is not dict or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63 or item['template']not in TEMPLATES or(item['metadata'],item['group'],item['count'])!=(0,4,1):raise ValueError('Owned finite singleton wisdom potion')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Wisdom potion owned bag slot')
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
    out=_ExistingWisdom(v);out._original=dict(v);return out

def validate_existing(item):
    if type(item)is not _ExistingWisdom or dict(item)!=item._original:raise ValueError('Unchanged owned wisdom reader required')
    read_existing(dict(item));return item

def request(payload):
    from els_server.protocol.career_messages import use_request
    return use_request(payload)

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.storage.wisdom_potions import recognizes,perform
    operation=s.shop_session_id+':wisdom-potion:'+str(account.uid)+':'+str(sequence)
    if not recognizes(store.path,account.uid,event.payload,operation):return None
    from els_server.domain.equipment_chip_flow import reset_authority
    from els_server.protocol.career_messages import use_ack
    from els_server.protocol.dungeon_messages import return_user_sync
    from els_server.storage.seal_quests import load_character
    root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None);registry=getattr(app,'registry',None);local_app=getattr(s,'_chip_reset_local_application',None)
    path=Path(store.path).resolve();uid=account.uid;aid=account.account_id;shop=s.shop_session_id;reward=account.reward_store
    def prepare(db):
        reset_authority(s)
        main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
        if(not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path or Path(store.path).resolve()!=path or Path(reward.path).resolve()!=path or not s.item_test or s.client_build!='dx11_260923'or s.role!='game'or s.phase!='town_ready'
            or not {0x28,0x225,0x227}<=s.completed or type(sequence)is not int or not 0<sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.account is not account or account.store is not store or account.root is not root or account.reward_store is not reward
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity or getattr(app,'registry',None)is not registry or getattr(s,'_chip_reset_local_application',None)is not local_app
            or(account.uid,account.account_id,s.shop_session_id)!=(uid,aid,shop)):raise ValueError('Wisdom current original writer/actor')
    def notice(db,items,balances):
        character=load_character(db,uid,aid)
        # Original complete D9 unit; empty acquisition vector. No fabricated
        # NPC death, dungeon clear, quest or ERP source is used to show EXP.
        return return_user_sync(account.get_location(),account.get_skills(),balances,items,character)
    try:return perform(path,uid,aid,event.payload,operation,reward,prepare=prepare,notice=notice)
    except ValueError:return[use_ack(result=-1)]
