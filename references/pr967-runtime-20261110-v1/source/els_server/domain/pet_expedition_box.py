"""Approved local expedition box pools; no native odds are claimed.

The two boxes are the only region1 expedition rewards. Their contents are the
local pool approved on2026-10-31 in domain.pet_expedition.boxes, not a native
drop table: the client only declares the box identity and its life-page slot.
"""
import functools,hashlib

BOXES=(135984,135985)
RECORD_SHA256={135984:'d06047950e0861d6f9cb608ae2d5fd227c4b23336eb77911b9e10c967d0b062c',
               135985:'cc4920852f9f0b8e4c86705cd0bffef962586b9fff80838368c06b85f018720f'}
CONTENTS=frozenset((135977,135974))
POOL_TOTAL=10000


@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.domain.pet_expedition import boxes
    from els_server.game_data import client_data
    client=client_data();rows=boxes()
    if set(rows)!=set(BOXES):raise ValueError('Expedition box scope')
    approved={}
    for template,row in rows.items():
        item=client.item(template)
        entries=tuple(row['entries'])
        # selection_count0 means the original client never offers a choice; the
        # server is the only place a draw can happen.
        if (hashlib.sha256(item['record']).hexdigest()!=RECORD_SHA256[template]
                or row['group']!=21 or row['selection_count']!=0 or row.get('random')is not True
                or sum(e['weight']for e in entries)!=POOL_TOTAL
                or {e['template']for e in entries}!=CONTENTS
                or any(type(e['quantity'])is not int or e['quantity']!=1
                       or type(e['weight'])is not int or not 0<e['weight']<POOL_TOTAL
                       for e in entries)):
            raise ValueError('Expedition box approved pool')
        approved[template]=row
    return approved


def admitted():
    return frozenset(definitions())


def draw(template,randbelow):
    """One weighted pick inside the caller's writer; total is always10000."""
    row=definitions()[template]
    if not callable(randbelow):raise ValueError('Expedition box draw source')
    pick=randbelow(POOL_TOTAL)
    if type(pick)is not int or not 0<=pick<POOL_TOTAL:raise ValueError('Expedition box draw range')
    for entry in row['entries']:
        if pick<entry['weight']:return entry
        pick-=entry['weight']
    raise ValueError('Expedition box pool exhausted')


class _ExistingBox(dict):
    __slots__=('_original',)


def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    if (type(item)is not dict or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys
            or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63
            or item['template']not in BOXES or(item['metadata'],item['group'])!=(2,21)
            or not 0<item['count']<2**31):
        raise ValueError('Expedition box owned shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(21):raise ValueError('Expedition box slot')
    definitions();value=dict(item)
    if 'expires_at'in value:
        from els_server.domain.item_expiration import validate
        value['expires_at']=validate(value['expires_at'])
    if 'lock_until'in value:
        from els_server.domain.item_locks import validate
        value['lock_until']=validate(value['lock_until'])
    if 'sealed'in value or 'seal_used'in value:
        from els_server.storage.item_seals import validate
        validate(value.get('sealed',False),value.get('seal_used',0))
    result=_ExistingBox(value);result._original=dict(value);return result


def validate_existing(item):
    if type(item)is not _ExistingBox or dict(item)!=item._original:
        raise ValueError('Expedition box requires unchanged SQL reader')
    read_existing(dict(item));return item


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x559,0x196):return None
    account=getattr(s,'account',None);store=getattr(account,'store',None)
    if store is None:return None
    from els_server.protocol.ice_messages import preview_request,preview_ack
    from els_server.protocol.cube_messages import result
    from els_server.storage.pet_expedition_box import recognizes,open_box
    from els_server.domain.equipment_chip_flow import reset_authority
    operation=s.shop_session_id+':expedition-box:'+str(account.uid)+':'+str(sequence)
    if event.kind==0x559:
        try:request=preview_request(event.payload)
        except ValueError:return None
        if request.template not in admitted():return None
    elif not recognizes(store.path,account.uid,event.payload,operation):return None
    from pathlib import Path
    root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
    path=Path(store.path).resolve();uid=account.uid;aid=account.account_id;shop=s.shop_session_id
    def prepare(db):
        reset_authority(s)
        if (not s.item_test or s.client_build!='dx11_260923' or s.role!='game' or s.phase!='town_ready'
                or not {0x28,0x225,0x227}<=s.completed or type(sequence)is not int or not 0<sequence<2**32
                or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
                or s.account is not account or account.store is not store or account.root is not root
                or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity
                or(account.uid,account.account_id,s.shop_session_id)!=(uid,aid,shop)
                or Path(store.path).resolve()!=path):
            raise ValueError('Expedition box current actor/context')
    try:
        if event.kind==0x559:
            prepare(None)
            if request.keys not in((),(0,))or request.flag1 not in(0,1)or request.flag2 not in(0,1):
                raise ValueError('Expedition box preview mode')
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
            if not eligible:raise ValueError('Owned expedition box missing')
            s.ice_preview_ready=False;s.fixed_cube_preview_template=None
            row=definitions()[request.template]
            return[preview_ack(0,request.template,selection_count=0,
                entries=tuple((e['template'],0,e['quantity'])for e in row['entries']))]
        return open_box(path,uid,aid,event.payload,operation,prepare=prepare)
    except ValueError:
        return[preview_ack(-1,request.template)]if event.kind==0x559 else result(
            account.get_reward_balances()['ed'],code=-1)
