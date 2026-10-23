"""Existing single119335, exact thirteen caller choices; no producer or RNG."""
from pathlib import Path
import functools
import hashlib
import json
import sqlite3
from els_server.game_data import client_data, CLIENT_SHA

BOX = 119335
OUTPUTS = tuple(range(119222, 119235))
WRITER_ENABLED = True
DATA_SHA = 'accceca5b601d16f6b869c844652a2b7dd6d90e554fc199721eb2364c3e27e06'


@functools.lru_cache(maxsize=1)
def _data():
    raw = (Path(__file__).resolve().parents[1] / 'data/cartridge_selection_box.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Cartridge selection data identity')
    data = json.loads(raw)
    if (data['schema_version'] != 1 or data['client_sha256'] != CLIENT_SHA
            or data['catalog_sha256'] != client_data().manifest['catalog_sha256']
            or data['scope'] != 'existing-singleton-only-no-producer'
            or data['box']['template'] != BOX or data['box']['metadata'] != 0
            or data['box']['group'] != 4 or data['box']['max_stack'] != 1
            or data['box']['raw_max_semantics'] != 'UNKNOWN'
            or data['box']['max_stack_semantics'] != 'operation-guard-only-not-native-stack'
            or data['box']['read_count_wire_max'] != 2**31-1
            or data['box']['compatibility_policy'] != 'existing-singleton119335-reader-use-v1'
            or tuple(r['template'] for r in data['entries']) != OUTPUTS
            or any((r['quantity'], r['metadata'], r['group'], r['max_stack']) != (1,0,4,1)
                   for r in data['entries'])
            or data['random_rule'] != {'m_KeyItemID':0,'m_iGiveCount':1,'m_ItemID':BOX,
                'm_RequiredKeyCount':0,'m_UseCondition':1,'1':{'m_iItemGroupID':BOX,'m_cUnitClass':0}}):
        raise ValueError('Cartridge selection finite data contract')
    expected = '内含：\n' + '\n'.join('-' + r['name'] for r in data['entries']) + '\n中其中一个'
    if data['box']['description'].split('内含：\n', 1)[-1] != expected.split('内含：\n',1)[-1]:
        raise ValueError('Cartridge selection original choice text')
    return data


def box_definition():
    row = dict(_data()['box'])
    item = client_data().item(BOX)
    if (item['metadata'] != 0 or item['item_type'] != 7 or item['name'] != row['name']
            or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']):
        raise ValueError('Cartridge selection original box identity')
    return row


class _ExistingBox(dict):
    __slots__ = ('_original',)


def read_existing_box(item):
    """Preserve an owned legacy record; count wire width is not a stack rule."""
    keys = {'uid','template','metadata','count','group','slot'}
    optional = {'expires_at','lock_until','sealed','seal_used'}
    if (type(item) is not dict or set(item)-optional != keys
            or any(type(item[k]) is not int for k in keys)
            or not 1 <= item['uid'] < 2**63
            or (item['template'],item['metadata'],item['group']) != (BOX,0,4)
            or not 1 <= item['count'] <= 2**31-1):
        raise ValueError('Cartridge selection existing record identity/wire shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0 <= item['slot'] < wire_limit(4):
        raise ValueError('Cartridge selection existing record slot')
    box_definition()
    result = dict(item)
    if 'expires_at' in item:
        from els_server.domain.item_expiration import validate as validate_expiration
        result['expires_at'] = validate_expiration(item['expires_at'])
    if 'lock_until' in item:
        from els_server.domain.item_locks import validate as validate_lock
        result['lock_until'] = validate_lock(item['lock_until'])
    if 'sealed' in item or 'seal_used' in item:
        from els_server.storage.item_seals import validate as validate_seals
        validate_seals(item.get('sealed',False),item.get('seal_used',0))
    record = _ExistingBox(result)
    record._original = dict(record)
    return record


def validate_existing_box(item):
    """Native serializers validate an unchanged trusted SQL/container record."""
    if type(item) is not _ExistingBox or dict(item) != item._original:
        raise ValueError('Cartridge selection is read-only outside exact consumer')
    # Recheck the original fields; no returned ordinary dict can activate insert.
    read_existing_box(dict(item))
    return item


def relocate_existing_box(item, updated):
    """Only an already SQL-read whole UID may change its bag position.

    This finite adapter never changes count/UID/template/metadata or unknown
    state. Bank wrapper positions stay outside the original item record.
    """
    validate_existing_box(item)
    if (type(updated) is not dict
            or {k:v for k,v in item.items() if k not in ('group','slot')}
                != {k:v for k,v in updated.items() if k not in ('group','slot')}):
        raise ValueError('Cartridge box movement must retain whole instance')
    return read_existing_box(updated)


def entry():
    row = box_definition()
    from els_server.domain.cartridge_registration_rules import material
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
    for source in _data()['entries']:
        current = material(source['template'])
        if any(current[k] != source[k] for k in ('metadata','group','max_stack','record_sha256')):
            raise ValueError('Cartridge selection independent material reader')
        if (VERIFIED_TEMPLATES.get(source['template']), TEMPLATE_BAG_GROUPS.get(source['template']),
                TEMPLATE_MAX_STACKS.get(source['template'])) != (0,4,1):
            raise ValueError('Cartridge selection material reader is absent')
    return dict(row, selection_count=1, entries=[dict(r) for r in _data()['entries']])


def request(payload):
    from els_server.protocol.ice_messages import use_request
    if type(payload) is not bytes:
        raise ValueError('Cartridge selection request bytes')
    value = use_request(payload)
    if (value.option != 0 or any(v not in (0,1) for v in (value.flag1,value.flag2,value.flag3))
            or len(value.choices) != 1 or value.choices[0] not in OUTPUTS):
        raise ValueError('Cartridge selection exact one choice')
    entry()
    return value


def plain_box(item):
    allowed = {'uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_used'}
    return (type(item) in (dict,_ExistingBox) and not set(item)-allowed
            and (item.get('template'),item.get('metadata'),item.get('group'),item.get('count')) == (BOX,0,4,1)
            and type(item.get('count')) is int
            and item.get('sealed',False) is False and item.get('seal_used',0) == 0)


def _local_selected(session):
    from uuid import UUID
    from els_server.application import Application
    from els_server.domain.local_session import LocalAccount,LocalSession
    from els_server.storage.local_state import LocalState
    from els_server.storage.characters import Characters
    account=getattr(session,'account',None);root=getattr(account,'root',None)
    app=getattr(session,'_box119335_local_application',None)
    if (type(session) is not LocalSession or type(app) is not Application
        or getattr(session,'_box119335_local_live',None) is not True
        or app.config.mode!='local' or type(account) is not LocalAccount
        or type(root) is not LocalAccount or root.root is not root or app.account is not root
        or type(root.account_id) is not int or root.account_id!=1
        or root.character_accounts.get(account.uid) is not account
        or type(account.store) is not LocalState or account.store.uid!=account.uid
        or type(root.store) is not LocalState or root.store.uid!=root.uid
        or type(account.characters) is not Characters or root.characters is not account.characters
        or account.account_id!=root.account_id or account.characters.account_id!=account.account_id
        or session.role!='game' or not {0x28,0x225,0x227}<=session.completed):
        return False
    path=Path(account.store.path).resolve()
    if (Path(root.store.path).resolve()!=path or Path(account.characters.path).resolve()!=path
        or Path(app.config.state_file).resolve()!=path):return False
    token=session.shop_session_id
    try:return type(token) is str and str(UUID(token))==token and UUID(token).version==4
    except ValueError:return False


def selected(session):
    if getattr(session,'application',None) is None:return _local_selected(session)
    from els_server.domain.equipment_engrave_flow import current_lease
    return bool(getattr(session,'application',None) is not None and current_lease(session)
                and session.role == 'game' and 0x28 in session.completed
                and session.account.characters is not None and session.account.store is not None
                and session.account.store.uid == session.account.uid)


def _ready(session):
    return selected(session) and session.phase == 'town_ready'


def _envelope(event, sequence):
    return (type(sequence) is int and 1 <= sequence < 2**32
            and event.event_id == 0x202 and event.performers == (0,)
            and event.uid == 0xffffffffffffffff and event.target_uid == 0xffffffffffffffff
            and event.payload_mode == 0 and type(event.payload) is bytes)


class _BoxAuthority:
    """Capture actual account/store/session/envelope, not a payload grant flag."""
    def __init__(self, session, event, sequence, operation):
        self.session, self.account = session, session.account
        self.store = self.account.store
        self.owner, self.account_id = self.account.uid, self.account.account_id
        self.path, self.shop = Path(self.store.path).resolve(), session.shop_session_id
        self.event, self.sequence, self.operation = event, sequence, operation
        self.local_application = getattr(session,'_box119335_local_application',None)
        self.root = self.account.root
        self.payload = event.payload
        if not self():
            raise ValueError('Cartridge selection captured authority')

    def __call__(self):
        from els_server.storage.cartridge_selection_box import WRITER_ENABLED as STORAGE_WRITER
        s, a, e = self.session, self.account, self.event
        return bool(WRITER_ENABLED and STORAGE_WRITER and _ready(s) and s.account is a
                    and a.root is self.root and getattr(s,'_box119335_local_application',None) is self.local_application
                    and a.store is self.store and a.uid == self.owner and a.account_id == self.account_id
                    and self.store.uid == self.owner and Path(self.store.path).resolve() == self.path
                    and s.shop_session_id == self.shop and e.kind == 0x196
                    and self.operation == self.shop + ':' + str(self.owner) + ':cartridge-box119335:' + str(self.sequence)
                    and _envelope(e,self.sequence) and e.payload == self.payload)


class _BoxSource:
    """One removed owned box in this exact transaction authorizes one original grant."""
    def __init__(self, db, owner, account_id, payload, operation, authority):
        if type(db) is not sqlite3.Connection or type(authority) is not _BoxAuthority or not db.in_transaction:
            raise ValueError('Cartridge selection internal source')
        value = request(payload)
        self.db, self.owner, self.account_id = db, owner, account_id
        self.payload, self.operation, self.authority = payload, operation, authority
        self.uid, self.destination = value.uid, value.choices[0]
        self.phase, self.expected, self.write_mark = 'captured', None, None
        self.marker = 'cartridge_box_' + hashlib.sha256(operation.encode()).hexdigest()
        db.execute('SAVEPOINT ' + self.marker)
        self._check()
        self.before = self._rows()

    def _rows(self):
        return tuple(tuple(r) for r in self.db.execute(
            'SELECT uid,owner,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY uid',
            (self.owner,)))

    def _check(self):
        a, db = self.authority, self.db
        if (self.phase == 'closed' or not db.in_transaction or a.owner != self.owner
                or a.account_id != self.account_id or a.payload != self.payload or a.operation != self.operation
                or (request(self.payload).uid,request(self.payload).choices[0]) != (self.uid,self.destination)):
            raise ValueError('Cartridge selection source identity/transaction')
        from els_server.storage.cartridge_selection_box import _context
        _context(db,self.owner,self.account_id,a)
        # Missing marker after COMMIT/ROLLBACK/new BEGIN is rejection, never new permission.
        db.execute('RELEASE SAVEPOINT ' + self.marker)
        db.execute('SAVEPOINT ' + self.marker)

    def debit_complete(self):
        self._check()
        source = next((r for r in self.before if r[0] == self.uid), None)
        if self.phase != 'captured' or source is None or source[1:6] != (self.owner,BOX,0,1,4):
            raise ValueError('Cartridge selection singleton debit identity')
        self.expected = tuple(r for r in self.before if r[0] != self.uid)
        if self._rows() != self.expected:
            raise ValueError('Cartridge selection actual SQL debit')
        self.write_mark, self.phase = self.db.total_changes, 'debited'

    def _plan(self, plan):
        if (type(plan) is not list or len(plan) != 1 or type(plan[0]) is not dict
                or any(type(v) is not int for v in plan[0].values())
                or plan != [dict(template=self.destination,metadata=0,group=4,quantity=1)]):
            raise ValueError('Cartridge selection whole one-material plan')

    def bind_factory(self, db, owner, plan):
        self._check(); self._plan(plan)
        if (self.phase != 'debited' or db is not self.db or owner != self.owner
                or self.db.total_changes != self.write_mark or self._rows() != self.expected):
            raise ValueError('Cartridge selection original factory binding/reuse')
        self.phase = 'factory'

    def validate_plan(self, plan):
        self._check(); self._plan(plan)
        if self.phase != 'factory' or self.db.total_changes != self.write_mark or self._rows() != self.expected:
            raise ValueError('Cartridge selection plan phase')

    def consume_template(self, template):
        self.validate_plan([dict(template=template,metadata=0,group=4,quantity=1)])
        if template not in OUTPUTS:
            raise ValueError('Cartridge selection output identity')
        self.phase = 'spent'

    def close(self):
        if self.phase != 'closed':
            self.phase = 'closed'
            self.db.execute('RELEASE SAVEPOINT ' + self.marker)


def validate_source(source):
    if type(source) is not _BoxSource:
        raise ValueError('Cartridge selection private source required')
    return source


def handle(session, event, sequence):
    """Both native entries intercepted before generic cube/ice dispatch, also when closed."""
    if not (session.item_test and session.client_build == 'dx11_260923'
            and event.event_id == 0x202 and event.kind in (0x559,0x196)):
        return None
    from els_server.protocol.ice_messages import preview_request, preview_ack, use_request
    from els_server.protocol.cube_messages import result
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    if event.kind == 0x559:
        try:
            value = preview_request(event.payload)
        except (ValueError,TypeError):
            return None
        if value.template != BOX:
            return None
        session.fixed_cube_preview_template = None
        if not selected(session):
            return [preview_ack(-1,BOX)]
        try:
            from els_server.storage.cartridge_selection_box import WRITER_ENABLED as STORAGE_WRITER
            if (not WRITER_ENABLED or not STORAGE_WRITER or not _ready(session) or not _envelope(event,sequence)
                    or value.keys not in ((),(0,)) or value.flag1 not in (0,1) or value.flag2 not in (0,1)):
                raise ValueError('Cartridge selection preview context')
            item = next((i for i in session.account.get_inventory_snapshot()['items'] if plain_box(i)),None)
            if item is None:
                raise ValueError('Cartridge selection owned singleton missing')
            require_current(item); require_unlocked(item)
            row = entry()
            session.fixed_cube_preview_template = BOX
            session.ice_preview_ready = False
            return [preview_ack(0,BOX,selection_count=1,entries=tuple((r['template'],0,1) for r in row['entries']))]
        except (ValueError,sqlite3.Error):
            return [preview_ack(-1,BOX)]
    replayed_box = session.fixed_cube_operations.get((getattr(session.account,'uid',None),sequence)) == BOX
    cached = replayed_box or session.fixed_cube_preview_template == BOX
    try:
        value = use_request(event.payload)
    except (ValueError,TypeError):
        return result(0,code=-1) if cached else None
    if not selected(session):
        return result(0,code=-1) if cached else None
    item = next((i for i in session.account.get_inventory_snapshot()['items'] if i['uid'] == value.uid),None)
    if item is not None and item['template'] != BOX and not replayed_box:
        return None
    if (item is None or item['template'] != BOX) and not cached:
        return None
    ed = session.account.get_reward_balances()['ed']
    try:
        operation = session.shop_session_id + ':' + str(session.account.uid) + ':cartridge-box119335:' + str(sequence)
        authority = _BoxAuthority(session,event,sequence,operation)
        from els_server.storage.cartridge_selection_box import open_box
        answer = open_box(authority.path,authority.owner,event.payload,operation,
                          account_id=authority.account_id,authorize=authority)
        session.fixed_cube_operations[(authority.owner,sequence)] = BOX
        return answer
    except (ValueError,sqlite3.Error):
        return result(ed,code=-1)
