"""Six source-qualified manual selections; reference compatibility, not retail fees."""
from pathlib import Path
import functools
import hashlib
import json
import struct
from els_server.game_data import client_data, CLIENT_SHA

DATA_SHA = 'c78a30a1ec958234c63ac2965c01845176709078864a641de9a2ed35aa538c99'
POLICY = 'house40326-six-select-material-reference-v1'
SOURCE = 119216
DESTINATIONS = frozenset(range(119235, 119241))


@functools.lru_cache(maxsize=1)
def _definitions():
    raw = (Path(__file__).resolve().parents[1] / 'data/cartridge_exchange.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Cartridge exchange data identity')
    data = json.loads(raw)
    if (data['schema_version'] != 1 or data['policy_id'] != POLICY
            or data['official'] is not False or data['client_sha256'] != CLIENT_SHA
            or data['catalog_sha256'] != client_data().manifest['catalog_sha256']
            or data['house'] != 40326 or data['town'] != 1012 or data['scene'] != 1214
            or data['source'] != dict(template=SOURCE, metadata=2, group=3, max_stack=1000,
                                     record_sha256='ec98dcd5d39d9c740a3b617e79e7222d46f328c8c4554dac62a45a95e4eee29b')
            or data['economy'] != {'source_quantity': 100, 'destination_quantity': 1,
                                   'ed_delta': 0, 'quota_definition': None}):
        raise ValueError('Cartridge exchange finite source policy')
    expected = [(680+n, 119235+n, 16 if n < 2 else 17) for n in range(6)]
    if [(r['index'], r['destination'], r['raw_rate']) for r in data['recipes']] != expected:
        raise ValueError('Cartridge exchange exact six recipes')
    return data


def source_definition():
    definition = dict(_definitions()['source'])
    original = client_data().item(SOURCE)
    raw = original['record']
    if (original['metadata'] != 2 or original['item_type'] != 6
            or hashlib.sha256(raw).hexdigest() != definition['record_sha256']
            or struct.unpack_from('<H', raw, 16)[0] != 1000
            or struct.unpack_from('<II', raw, 4) != (0x22101002, 0x30)):
        raise ValueError('Cartridge exchange black-fragment definition')
    return definition


def catalog():
    data = _definitions()
    source_definition()
    # These independently reviewed readers are a composition prerequisite,
    # not six new registrations or collection writes in this exchange unit.
    from els_server.domain.cartridge_registration_rules import material
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
    if (VERIFIED_TEMPLATES.get(SOURCE), TEMPLATE_BAG_GROUPS.get(SOURCE),
            TEMPLATE_MAX_STACKS.get(SOURCE)) != (2, 3, 1000):
        raise ValueError('Cartridge exchange source reader is absent')
    for recipe in data['recipes']:
        destination = recipe['destination']
        definition = material(destination)
        if (definition['metadata'], definition['group'], definition['max_stack'],
                definition['record_sha256']) != (0, 4, 1, recipe['record_sha256']):
            raise ValueError('Cartridge exchange singleton reader identity')
        if (VERIFIED_TEMPLATES.get(destination), TEMPLATE_BAG_GROUPS.get(destination),
                TEMPLATE_MAX_STACKS.get(destination)) != (0, 4, 1):
            raise ValueError('Cartridge exchange singleton reader is absent')
    return data


def request(payload):
    from els_server.protocol.purifier_exchange_messages import ExchangeRequest
    if not isinstance(payload, bytes) or len(payload) != 37:
        raise ValueError('Cartridge exchange request length')
    value = ExchangeRequest(*struct.unpack('>iQiiiiiBi', payload))
    if (value.house != 40326 or value.source_uid != 0 or value.source != SOURCE
            or value.source_quantity != 100 or value.destination not in DESTINATIONS
            or value.exchange_type != 3 or value.quantity != 1
            or value.native_flag != 1 or value.native_index != 0):
        raise ValueError('Unsupported Cartridge manual selection')
    catalog()
    return value


def plain_source(item):
    allowed = {'uid', 'template', 'metadata', 'count', 'group', 'slot',
               'expires_at', 'lock_until', 'sealed', 'seal_used'}
    return (not set(item) - allowed and item.get('template') == SOURCE
            and item.get('metadata') == 2 and item.get('group') == 3
            and type(item.get('count')) is int and 1 <= item['count'] <= 1000
            and item.get('sealed', False) is False and item.get('seal_used', 0) == 0)


class _SelectAuthority:
    """Captured native request and selected session, never a grant payload flag."""
    def __init__(self, session, event, sequence, operation, current):
        self.session, self.account = session, session.account
        self.store = self.account.store
        self.owner, self.account_id = self.account.uid, self.account.account_id
        self.path = Path(self.store.path).resolve()
        self.shop = session.shop_session_id
        self.event, self.sequence, self.operation = event, sequence, operation
        self.payload = event.payload
        self.current = current
        if not self():
            raise ValueError('Cartridge exchange captured authority')

    def __call__(self):
        from els_server.storage.cartridge_exchange import WRITER_ENABLED
        from els_server.domain.cartridge_exchange_flow import WRITER_ENABLED as FLOW_WRITER_ENABLED
        session, account, event = self.session, self.account, self.event
        return bool(WRITER_ENABLED and FLOW_WRITER_ENABLED and session.account is account
                    and account.store is self.store and account.uid == self.owner
                    and account.account_id == self.account_id
                    and self.store.uid == self.owner and Path(self.store.path).resolve() == self.path
                    and session.shop_session_id == self.shop
                    and self.operation == self.shop + ':' + str(self.owner)
                        + ':cartridge-exchange40326:' + str(self.sequence)
                    and type(self.sequence) is int and 1 <= self.sequence < 2**32
                    and event.event_id == 0x202 and event.kind == 0x223
                    and event.performers == (0,) and event.uid == 0xffffffffffffffff
                    and event.target_uid == 0xffffffffffffffff and event.payload_mode == 0
                    and type(event.payload) is bytes and event.payload == self.payload
                    and self.current() is True)


class _SelectSource:
    """One SQL-proven debit, one whole singleton plan, one original factory call."""
    def __init__(self, db, owner, account_id, payload, operation, authority):
        import sqlite3
        if type(db) is not sqlite3.Connection or type(authority) is not _SelectAuthority:
            raise ValueError('Cartridge exchange internal source type')
        self.db, self.owner, self.account_id = db, owner, account_id
        self.authority, self.operation, self.payload = authority, operation, payload
        self.destination = request(payload).destination
        self.phase = 'captured'
        if not db.in_transaction:
            raise ValueError('Cartridge exchange source requires original transaction')
        self.savepoint = 'cartridge_select_' + hashlib.sha256(operation.encode('utf8')).hexdigest()
        db.execute('SAVEPOINT ' + self.savepoint)
        self._check()
        self.before = self._rows()
        self.expected = None
        self.write_mark = None

    def _rows(self):
        return tuple(tuple(row) for row in self.db.execute(
            'SELECT uid,owner,template,metadata,count,bag_group,slot FROM inventory_items '
            'WHERE owner=? ORDER BY uid', (self.owner,)))

    def _check(self):
        authority, db = self.authority, self.db
        if (self.phase == 'closed' or not db.in_transaction
                or authority.owner != self.owner or authority.account_id != self.account_id
                or authority.operation != self.operation or authority.payload != self.payload
                or request(self.payload).destination != self.destination):
            raise ValueError('Cartridge exchange source identity/transaction')
        main = [row[2] for row in db.execute('PRAGMA database_list') if row[1] == 'main']
        if len(main) != 1 or Path(main[0]).resolve() != authority.path:
            raise ValueError('Cartridge exchange source store')
        # Reuse complete owner/lifecycle/qualification/location checks and the
        # originally captured current lease/root/envelope callback, not a new actor.
        from els_server.storage.cartridge_exchange import _context, WRITER_ENABLED
        if not WRITER_ENABLED:
            raise ValueError('Cartridge exchange source writer closed')
        _context(db, self.owner, self.account_id, authority)
        # A committed/rolled-back transaction loses this marker even if the
        # same connection starts another transaction with identical rows.
        # RELEASE must succeed before recreating it; failure never retries.
        db.execute('RELEASE SAVEPOINT ' + self.savepoint)
        db.execute('SAVEPOINT ' + self.savepoint)

    def debit_complete(self, debits):
        self._check()
        if self.phase != 'captured' or type(debits) is not list or not debits:
            raise ValueError('Cartridge exchange source debit phase')
        expected = {row[0]: row for row in self.before}
        seen, total = set(), 0
        for uid, take in debits:
            row = expected.get(uid)
            if (type(uid) is not int or type(take) is not int or uid in seen
                    or row is None or row[1:4] != (self.owner, SOURCE, 2)
                    or row[5] != 3 or not 1 <= take <= row[4] <= 1000):
                raise ValueError('Cartridge exchange source debit rows')
            seen.add(uid)
            total += take
            if take == row[4]:
                del expected[uid]
            else:
                expected[uid] = row[:4] + (row[4] - take,) + row[5:]
        self.expected = tuple(expected[uid] for uid in sorted(expected))
        if total != 100 or self._rows() != self.expected:
            raise ValueError('Cartridge exchange source SQL debit mismatch')
        self.write_mark = self.db.total_changes
        self.phase = 'debited'

    def _plan(self, plan):
        if (type(plan) is not list or len(plan) != 1 or type(plan[0]) is not dict
                or any(type(v) is not int for v in plan[0].values())
                or plan != [dict(template=self.destination, metadata=0, group=4, quantity=1)]):
            raise ValueError('Cartridge exchange whole singleton plan')

    def bind_factory(self, db, owner, plan):
        self._check()
        self._plan(plan)
        if (self.phase != 'debited' or db is not self.db or owner != self.owner
                or self.db.total_changes != self.write_mark or self._rows() != self.expected):
            raise ValueError('Cartridge exchange source factory binding/reuse')
        self.phase = 'factory'

    def validate_plan(self, plan):
        self._check()
        self._plan(plan)
        if (self.phase != 'factory' or self.db.total_changes != self.write_mark
                or self._rows() != self.expected):
            raise ValueError('Cartridge exchange source plan phase')

    def consume_template(self, template):
        self.validate_plan([dict(template=template, metadata=0, group=4, quantity=1)])
        if template not in DESTINATIONS:
            raise ValueError('Cartridge exchange source output')
        self.phase = 'spent'

    def close(self):
        if self.phase != 'closed':
            self.phase = 'closed'
            self.db.execute('RELEASE SAVEPOINT ' + self.savepoint)


def validate_select_source(source):
    if type(source) is not _SelectSource:
        raise ValueError('Cartridge exchange internal source required')
    return source
