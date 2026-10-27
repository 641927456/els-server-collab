"""Exact679 owned20fragment -> oneBOX; finite nonretail compatibility."""
from pathlib import Path
import functools
import hashlib
import json
import struct
from els_server.game_data import client_data, CLIENT_SHA

DATA_SHA = 'b94429937b28a6d382e2383639a966ce66bc7ddcc65a30433b8e44278af837fb'
POLICY = 'house40326-recipe679-owned20-single-box-compat-v1'
SOURCE = 119216
BOX = 119335


@functools.lru_cache(maxsize=1)
def catalog():
    raw = (Path(__file__).resolve().parents[1] / 'data/cartridge_recipe679.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Recipe679 data identity')
    d = json.loads(raw)
    if (d['schema_version'] != 1 or d['policy_id'] != POLICY or d['official'] is not False
            or d['client_sha256'] != CLIENT_SHA
            or d['catalog_sha256'] != client_data().manifest['catalog_sha256']
            or d['request'] != [40326,0,SOURCE,20,0,1,1,1,0]
            or d['economy'] != {'source_quantity':20,'destination_quantity':1,'ed_delta':0}
            or d['recipe'] != {'index':679,'house':40326,'type':1,'source':SOURCE,
                               'destination':BOX,'server_group':-1,'period':0,'category':0,'raw_rate':100}):
        raise ValueError('Recipe679 finite policy')
    from els_server.domain.cartridge_exchange_rules import source_definition
    from els_server.domain.cartridge_selection_box import box_definition
    source, box = source_definition(), box_definition()
    if (source != d['source'] or box['record_sha256'] != d['box_record_sha256']
            or (box['template'],box['metadata'],box['group'],box['max_stack']) != (BOX,0,4,1)):
        raise ValueError('Recipe679 source/BOX dependency')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS
    if VERIFIED_TEMPLATES.get(BOX) not in (None,0) or (TEMPLATE_BAG_GROUPS.get(BOX),TEMPLATE_MAX_STACKS.get(BOX)) != (4,1):
        raise ValueError('Recipe679 requires private BOX reader, not generic grant')
    if (VERIFIED_TEMPLATES.get(SOURCE),TEMPLATE_BAG_GROUPS.get(SOURCE),TEMPLATE_MAX_STACKS.get(SOURCE)) != (2,3,1000):
        raise ValueError('Recipe679 source reader missing')
    return d


def request(payload):
    from els_server.protocol.purifier_exchange_messages import ExchangeRequest
    if type(payload) is not bytes or len(payload) != 37:
        raise ValueError('Recipe679 request length')
    v = ExchangeRequest(*struct.unpack('>iQiiiiiBi',payload))
    if tuple(v.__dict__.values()) != (40326,0,SOURCE,20,0,1,1,1,0):
        raise ValueError('Recipe679 exact request fields')
    catalog()
    return v


def plain_source(item):
    from els_server.domain.cartridge_exchange_rules import plain_source as original_plain
    return original_plain(item)


class _RecipeAuthority:
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
        from els_server.storage.cartridge_recipe679 import WRITER_ENABLED
        from els_server.domain.cartridge_recipe679_flow import WRITER_ENABLED as FLOW_WRITER_ENABLED
        from els_server.domain.cartridge_exchange_flow import _context as canonical_context
        session, account, event = self.session, self.account, self.event
        return bool(WRITER_ENABLED and FLOW_WRITER_ENABLED and session.item_test
                    and session.client_build == 'dx11_260923' and canonical_context(session)
                    and session.account is account
                    and account.store is self.store and account.uid == self.owner
                    and account.account_id == self.account_id
                    and self.store.uid == self.owner and Path(self.store.path).resolve() == self.path
                    and session.shop_session_id == self.shop
                    and self.operation == self.shop + ':' + str(self.owner)
                        + ':cartridge-recipe679:' + str(self.sequence)
                    and type(self.sequence) is int and 1 <= self.sequence < 2**32
                    and event.event_id == 0x202 and event.kind == 0x223
                    and event.performers == (0,) and event.uid == 0xffffffffffffffff
                    and event.target_uid == 0xffffffffffffffff and event.payload_mode == 0
                    and type(event.payload) is bytes and event.payload == self.payload
                    and self.current() is True)


class _RecipeSource:
    """One SQL-proven debit, one whole singleton plan, one original factory call."""
    def __init__(self, db, owner, account_id, payload, operation, authority):
        import sqlite3
        if type(db) is not sqlite3.Connection or type(authority) is not _RecipeAuthority:
            raise ValueError('Cartridge exchange internal source type')
        self.db, self.owner, self.account_id = db, owner, account_id
        self.authority, self.operation, self.payload = authority, operation, payload
        request(payload)
        self.destination = BOX
        self.phase = 'captured'
        if not db.in_transaction:
            raise ValueError('Cartridge exchange source requires original transaction')
        self.savepoint = 'cartridge_select_' + hashlib.sha256(operation.encode('utf8')).hexdigest()
        db.execute('SAVEPOINT ' + self.savepoint)
        self._check()
        self.before = self._rows()
        self.expected = None
        row = db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()
        if row is None or type(row[0]) is not int or not 1 <= row[0] < 2**63-1:
            raise ValueError('Recipe679 original UID sequence')
        self.expected_uid = row[0]
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
                or request(self.payload).destination != 0 or self.destination != BOX):
            raise ValueError('Cartridge exchange source identity/transaction')
        main = [row[2] for row in db.execute('PRAGMA database_list') if row[1] == 'main']
        if len(main) != 1 or Path(main[0]).resolve() != authority.path:
            raise ValueError('Cartridge exchange source store')
        # Reuse complete owner/lifecycle/qualification/location checks and the
        # originally captured current lease/root/envelope callback, not a new actor.
        from els_server.storage.cartridge_recipe679 import _context, WRITER_ENABLED
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
        if total != 20 or self._rows() != self.expected:
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
        if template not in (BOX,):
            raise ValueError('Cartridge exchange source output')
        self.phase = 'spent'

    def admit_instance(self, item):
        # This is the sole factory bridge for a newly source-authorized BOX.
        # It does not accept an arbitrary dict through the global validator.
        self._check()
        if (self.phase != 'spent' or type(item) is not dict
                or set(item) != {'uid','template','metadata','count','group','slot'}
                or any(type(v) is not int for v in item.values())
                or (item['uid'],item['template'],item['metadata'],item['count'],item['group'])
                    != (self.expected_uid,BOX,0,1,4)
                or self.db.total_changes != self.write_mark or self._rows() != self.expected
                or self.db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()
                    != (self.expected_uid,)):
            raise ValueError('Recipe679 one original factory instance')
        from els_server.domain.cartridge_selection_box import read_existing_box
        admitted = read_existing_box(item)
        self.phase = 'instance'
        return admitted

    def close(self):
        if self.phase != 'closed':
            self.phase = 'closed'
            self.db.execute('RELEASE SAVEPOINT ' + self.savepoint)


def validate_recipe_source(source):
    if type(source) is not _RecipeSource:
        raise ValueError('Cartridge exchange internal source required')
    return source
