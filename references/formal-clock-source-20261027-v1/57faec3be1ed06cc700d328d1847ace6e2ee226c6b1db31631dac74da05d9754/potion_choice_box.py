"""One original owned potion choice box, using the approved exact output mapping."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType

BOXES=(303673,)
OUTPUTS=(710003,710284)
PAYLOAD_SHA='23d911f6f400eb3c4645c142e2e6d2a3450564d58fe09753d4a10700ddd47299'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/potion_choice_box.json').read_bytes()
    d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or d['client_sha256']!=CLIENT_SHA or tuple(r['template']for r in d['rows'])!=BOXES:
        raise ValueError('Potion choice box source binding')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.quick_bindings import item_binding
    if d['local_mapping']!=[dict(template=710003,quantity=100),dict(template=710284,quantity=130)]or d['new_box_sources']:raise ValueError('Potion choice approved mapping')
    for r in d['rows']:
        t=r['template'];item=client_data().item(t)
        if(hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']or item['record'].hex()!=r['record_hex']or(item['item_type'],item['metadata'],item['flags4'],item['flags8'])!=(7,0,0x401002,56)
            or r['selection_count']!=1 or tuple((e['template'],e['quantity'])for e in r['entries'])!=((710003,100),(710284,130))
            or r['random_rule']!=dict(m_KeyItemID=0,m_iGiveCount=1,m_ItemID=t,m_RequiredKeyCount=0,m_UseCondition=1,**{'1':dict(m_iItemGroupID=999187143,m_cUnitClass=0)})):
            raise ValueError('Potion choice original input and approved exact outputs')
        for e in r['entries']:
            out=client_data().item(e['template'])
            if((VERIFIED_TEMPLATES.get(e['template']),TEMPLATE_BAG_GROUPS.get(e['template']),TEMPLATE_MAX_STACKS.get(e['template']))!=(2,6,999)
                or out['name']!=e['name']or hashlib.sha256(out['record']).hexdigest()!=e['record_sha256']or item_binding(e['template'])!=e['binding']or e['name']+str(e['quantity'])+'个'not in r['description']):raise ValueError('Potion choice native output identity')
    return MappingProxyType({r['template']:MappingProxyType(r)for r in d['rows']})

def admitted():return frozenset(t for t,r in definitions().items()if r.get('admitted',True))

class _ExistingBox(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    if (type(item)is not dict or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys
        or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63
        or item['template']not in BOXES or(item['metadata'],item['group'])!=(0,4)or not 0<item['count']<2**31):
        raise ValueError('Existing teacher bundle SQL shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(4):raise ValueError('Existing teacher bundle slot')
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
    result=_ExistingBox(v);result._original=dict(v);return result

def validate_existing(item):
    if type(item)is not _ExistingBox or dict(item)!=item._original:raise ValueError('Potion choice box requires unchanged SQL reader')
    read_existing(dict(item));return item

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x559,0x196):return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.protocol.ice_messages import preview_request,preview_ack,use_request
    from els_server.protocol.cube_messages import result
    from els_server.storage.potion_choice_box import recognizes,open_box
    from els_server.domain.equipment_chip_flow import reset_authority
    operation=s.shop_session_id+':potion-choice:'+str(account.uid)+':'+str(sequence)
    if event.kind==0x559:
        try:request=preview_request(event.payload)
        except ValueError:return None
        if request.template not in admitted():return None
    elif not recognizes(store.path,account.uid,event.payload,operation):return None
    root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
    path=Path(store.path).resolve();uid=account.uid;aid=account.account_id;shop=s.shop_session_id
    def prepare(db):
        reset_authority(s)
        if (not s.item_test or s.client_build!='dx11_260923' or s.role!='game' or s.phase!='town_ready'
            or not {0x28,0x225,0x227}<=s.completed or type(sequence)is not int or not 0<sequence<2**32
            or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
            or s.account is not account or account.store is not store or account.root is not root
            or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
            or(account.uid,account.account_id,s.shop_session_id)!=(uid,aid,shop)or Path(store.path).resolve()!=path):
            raise ValueError('Potion choice box current actor/context')
    try:
        if event.kind==0x559:
            prepare(None)
            if request.keys not in((),(0,))or request.flag1 not in(0,1)or request.flag2 not in(0,1):raise ValueError('Potion choice box preview mode')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            items=[i for i in account.get_inventory_snapshot()['items']if i['template']==request.template]
            eligible=[]
            for i in items:
                try:
                    validate_existing(i);require_current(i);require_unlocked(i)
                    if i.get('sealed',False)or i.get('seal_used',0):continue
                    eligible.append(i)
                except ValueError:continue
            if not eligible:raise ValueError('Owned teacher elixir bundle missing')
            s.ice_preview_ready=False;s.fixed_cube_preview_template=None
            r=definitions()[request.template]
            return[preview_ack(0,request.template,selection_count=1,entries=tuple((e['template'],0,e['quantity'])for e in r['entries']))]
        return open_box(path,uid,aid,event.payload,operation,prepare=prepare)
    except ValueError:
        return[preview_ack(-1,request.template)]if event.kind==0x559 else result(account.get_reward_balances()['ed'],code=-1)
