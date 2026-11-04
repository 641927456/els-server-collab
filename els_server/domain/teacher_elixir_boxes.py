"""Two original owned teacher bundles, with their exact three listed contents."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType

BOXES=(715920,718310)
OUTPUTS=(710206,710207,710210)
PAYLOAD_SHA='478c867f98e270138e6f8b893baf08e2cbd26b9bc4f71f9a8b1e7c6716de4025'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/teacher_elixir_boxes.json').read_bytes()
    d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or d['client_sha256']!=CLIENT_SHA or tuple(r['template']for r in d['rows'])!=BOXES:
        raise ValueError('Teacher elixir bundle source binding')
    from els_server.domain.elixir_items import ITEMS
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    for r in d['rows']:
        t=r['template'];item=client_data().item(t)
        if (hashlib.sha256(item['record']).hexdigest()!=r['record_sha256'] or item['record'].hex()!=r['record_hex']
            or (item['item_type'],item['metadata'],item['flags4'],item['flags8'])!=(7,0,0x401002,56)
            or r['quantity']!=(15 if t==715920 else 5) or tuple(e['template']for e in r['entries'])!=OUTPUTS
            or any(e['quantity']!=r['quantity']for e in r['entries']) or r['random_rule']!=dict(m_KeyItemID=0,m_iGiveCount=0,m_ItemID=t,m_RequiredKeyCount=0,m_UseCondition=1,**{'1':dict(m_iItemGroupID=t,m_cUnitClass=0)})):
            raise ValueError('Teacher elixir bundle exact original contents')
        for e in r['entries']:
            out=client_data().item(e['template'])
            if (e['template']not in ITEMS or VERIFIED_TEMPLATES.get(e['template'])!=2 or TEMPLATE_BAG_GROUPS.get(e['template'])!=4
                or out['name']!=e['name'] or hashlib.sha256(out['record']).hexdigest()!=e['record_sha256']):
                raise ValueError('Teacher elixir output source changed')
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
    if type(item)is not _ExistingBox or dict(item)!=item._original:raise ValueError('Teacher bundle requires unchanged SQL reader')
    read_existing(dict(item));return item

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x559,0x196):return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.protocol.ice_messages import preview_request,preview_ack,use_request
    from els_server.protocol.cube_messages import result
    from els_server.storage.teacher_elixir_boxes import recognizes,open_box
    from els_server.domain.equipment_chip_flow import reset_authority
    operation=s.shop_session_id+':teacher-elixir:'+str(account.uid)+':'+str(sequence)
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
            raise ValueError('Teacher elixir bundle current actor/context')
    try:
        if event.kind==0x559:
            prepare(None)
            if request.keys not in((),(0,))or request.flag1 not in(0,1)or request.flag2 not in(0,1):raise ValueError('Teacher bundle preview mode')
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
            return[preview_ack(0,request.template,selection_count=0,entries=tuple((e['template'],0,e['quantity'])for e in r['entries']))]
        return open_box(path,uid,aid,event.payload,operation,prepare=prepare)
    except ValueError:
        return[preview_ack(-1,request.template)]if event.kind==0x559 else result(account.get_reward_balances()['ed'],code=-1)
