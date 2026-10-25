"""Private authority for one actual owned-cube debit in the current SQL transaction."""
import secrets
import sqlite3


class _OwnedCubeSource:
    def __init__(self, db, owner, item, output):
        from els_server.domain.regional_boss_cubes_legacy import catalog, require_primary
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        from els_server.storage.inventory_state import load_items
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        if type(db) is not sqlite3.Connection or not db.in_transaction:
            raise ValueError('Regional cube actual SQL transaction required')
        row = catalog().get(item['template'])
        if row is None or output not in row['entries']:
            raise ValueError('Regional cube exact disclosed output')
        if item not in load_items(db,owner) or item['group'] != 4:
            raise ValueError('Regional cube exact owned UID required')
        role = db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        if role is None:
            raise ValueError('Regional cube owner missing')
        require_primary(row,*role); require_current(item); require_unlocked(item)
        self.db,self.owner,self.item = db,owner,dict(item)
        self.plan = [dict(template=output['template'],metadata=VERIFIED_TEMPLATES[output['template']],
                          group=TEMPLATE_BAG_GROUPS[output['template']],quantity=output['quantity'])]
        self.before = self._rows()
        self.marker = 'regional_cube_' + secrets.token_hex(16)
        self.phase = 'captured'
        db.execute('SAVEPOINT ' + self.marker)

    def _rows(self):
        return tuple(tuple(r) for r in self.db.execute(
            'SELECT uid,owner,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY uid',
            (self.owner,)))

    def _check(self):
        if self.phase == 'closed' or not self.db.in_transaction:
            raise ValueError('Regional cube expired authority')
        # A commit/rollback followed by BEGIN must not resurrect this authority.
        self.db.execute('RELEASE SAVEPOINT ' + self.marker)
        self.db.execute('SAVEPOINT ' + self.marker)

    def debit_complete(self):
        self._check()
        expected = []
        for r in self.before:
            if r[0] != self.item['uid']:
                expected.append(r)
            elif r[4] > 1:
                expected.append((*r[:4],r[4]-1,*r[5:]))
        if self.phase != 'captured' or self._rows() != tuple(expected):
            raise ValueError('Regional cube exact SQL debit required')
        self.expected,self.write_mark,self.phase = tuple(expected),self.db.total_changes,'debited'

    def _plan(self, plan):
        if type(plan) is not list or plan != self.plan:
            raise ValueError('Regional cube exact one-draw grant plan')

    def bind_factory(self, db, owner, plan):
        self._check(); self._plan(plan)
        if (db is not self.db or owner != self.owner or self.phase != 'debited'
                or self.db.total_changes != self.write_mark or self._rows() != self.expected):
            raise ValueError('Regional cube factory identity/reuse')
        self.phase = 'factory'

    def validate_plan(self, plan):
        self._check(); self._plan(plan)
        if (self.phase != 'factory' or self.db.total_changes != self.write_mark
                or self._rows() != self.expected):
            raise ValueError('Regional cube grant phase')

    def consume_template(self, template):
        self.validate_plan(self.plan)
        if type(template) is not int or template != self.plan[0]['template']:
            raise ValueError('Regional cube output outside original draw')
        self.phase = 'spent'

    def verify_after(self):
        self._check()
        if self.phase != 'spent':
            raise ValueError('Regional cube grant did not consume its authority')
        self.phase = 'closed'
        self.db.execute('RELEASE SAVEPOINT ' + self.marker)


def validate_source(source):
    if type(source) is not _OwnedCubeSource:
        raise ValueError('Regional cube private owned source required')
    return source
