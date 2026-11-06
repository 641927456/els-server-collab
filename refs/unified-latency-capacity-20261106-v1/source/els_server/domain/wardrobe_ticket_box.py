"""Existing715036 only; six permanent tickets under the owner's2026-10-23 rule.

The raw KIM maximum remains unknown. The private reader preserves the saved
signed count; the ordinary stack tables below this reader are not grant rights.
"""
import functools
import hashlib
from types import MappingProxyType
from els_server.game_data import client_data

BOX = 715036
OUTPUTS = tuple(range(714357,714363))
BOX_RECORD_SHA = '558eb4d9c256864c35d279c3ab3703051c2dfc96ee46a1cc6022bc6d760f465b'
OUTPUT_RECORD_SHAS = (
    '23650b06e1f261f9b0aa4a9830fa352c0b9ac42f2e506cc726d6b9423393001e',
    'cb635e3d59259e53649f07b1ecd4bd2c5825bd3ac6c1f835c1fcec9926c9fcc3',
    '35e0436ec18f58240f11d7ce694bbb28a950b5ee388d012219112d94dcc795de',
    '4044faf5e7dab6a4027512236feb6b4083079530f0a99340a7253878a3f43d41',
    '3e406dbe5af361e900132741d3f026411f61c9e1c0a4f290c78d77424a80d665',
    '168b8566609d9d58a3815f85183aa148994d5cccdaf176b2bd6d99fface10e64',
)


@functools.lru_cache(maxsize=1)
def box_definition():
    item = client_data().item(BOX)
    if (item['id'] != BOX or item['metadata'] != 0 or item['item_type'] != 7
            or item['name'] != '[科宝]魔法衣橱券（第6次）宝箱'
            or hashlib.sha256(item['record']).hexdigest() != BOX_RECORD_SHA):
        raise ValueError('Existing wardrobe box source identity')
    return MappingProxyType(dict(template=BOX,metadata=0,group=4,
        name=item['name'],record_sha256=BOX_RECORD_SHA,
        raw_max_semantics='UNKNOWN',read_count_wire_max=2**31-1,
        existing_owned_only=True))


def entry():
    from els_server.domain.wardrobe_extensions import catalog
    definitions = catalog()['consumables']
    outputs = []
    for template,checksum in zip(OUTPUTS,OUTPUT_RECORD_SHAS):
        row = definitions.get(str(template))
        if (row is None or (row['template'],row['metadata'],row['group'],row['max_stack']) != (template,0,4,1)
                or row['record_sha256'] != checksum):
            raise ValueError('Existing generation6 wardrobe ticket definition changed')
        outputs.append(MappingProxyType(dict(template=template,quantity=1,name=row['name'])))
    return dict(box_definition(),selection_count=0,entries=tuple(outputs))


class _ExistingWardrobeBox(dict):
    __slots__ = ('_original',)


def read_existing_box(item):
    """Preserve an unchanged SQL-read old box; wire count is not a stack policy."""
    keys = {'uid','template','metadata','count','group','slot'}
    optional = {'expires_at','lock_until','sealed','seal_used'}
    if (type(item) is not dict or set(item)-optional != keys
            or any(type(item[k]) is not int for k in keys)
            or not 1 <= item['uid'] < 2**63
            or (item['template'],item['metadata'],item['group']) != (BOX,0,4)
            or not 1 <= item['count'] <= 2**31-1):
        raise ValueError('Existing wardrobe box identity or wire shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0 <= item['slot'] < wire_limit(4):
        raise ValueError('Existing wardrobe box slot')
    box_definition()
    value = dict(item)
    if 'expires_at' in item:
        from els_server.domain.item_expiration import validate
        value['expires_at'] = validate(item['expires_at'])
    if 'lock_until' in item:
        from els_server.domain.item_locks import validate
        value['lock_until'] = validate(item['lock_until'])
    if 'sealed' in item or 'seal_used' in item:
        from els_server.storage.item_seals import validate
        validate(item.get('sealed',False),item.get('seal_used',0))
    record = _ExistingWardrobeBox(value)
    record._original = dict(record)
    return record


def validate_existing_box(item):
    if type(item) is not _ExistingWardrobeBox or dict(item) != item._original:
        raise ValueError('Existing wardrobe box is read-only outside its consumer')
    read_existing_box(dict(item))
    return item


def require_session_context(session,event,sequence):
    """Only this box uses the existing current-lease item envelope checks."""
    from els_server.domain.equipment_chip_flow import current_lease
    account = session.account
    if (not session.item_test or session.client_build != 'dx11_260923'
            or session.role != 'game' or session.phase != 'town_ready'
            or account.characters is None or account.store is None
            or account.store.uid != account.uid
            or type(account.account_id) is not int or not 1 <= account.account_id < 2**63
            or type(sequence) is not int or not 1 <= sequence < 2**32
            or event.event_id != 0x202 or event.kind not in (0x559,0x196)
            or event.performers not in ((),(0,))
            or event.uid != 0xffffffffffffffff or event.target_uid != 0xffffffffffffffff
            or event.payload_mode != 0 or not current_lease(session)):
        raise ValueError('Existing wardrobe box session or lease')
