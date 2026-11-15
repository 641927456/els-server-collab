"""An exact NPC output budget, valid only in its original material transaction."""
from collections import Counter
import json,sqlite3

_SEAL=object()
def _key(row):return json.dumps(row,sort_keys=True,separators=(',',':'))

class _Source:
    def __init__(self,seal,db,owner,operation,rows,plan,guard):
        if seal is not _SEAL:raise ValueError('Private NPC source constructor')
        self.seal=seal;self.db=db;self.owner=owner;self.operation=operation;self.rows=rows
        self.remaining=Counter(_key(row)for row in plan);self.plan=[dict(row)for row in plan];self.bound=None;self.guard=guard
    def current(self):
        if self.seal is not _SEAL or not self.db.in_transaction:raise ValueError('NPC source outside transaction')
        self.guard()
        return self
    def bind_factory(self,db,owner,plan):
        self.current()
        if db is not self.db or owner!=self.owner:raise ValueError('NPC source writer/owner mismatch')
        wanted=Counter(_key(row)for row in plan)
        if wanted-self.remaining:raise ValueError('NPC source exceeds original award plan')
        self.remaining.subtract(wanted);self.bound=[dict(row)for row in plan]
    def validate_plan(self,plan):
        self.current()
        if plan!=self.bound:raise ValueError('NPC source grant plan changed')
        return self
    def validate_template(self,template):
        self.current()
        if template not in{row['template']for row in(self.plan if self.bound is None else self.bound)}:
            raise ValueError('NPC template outside bound factory plan')
        return True
    def finish(self):
        self.current()
        if any(self.remaining.values()):raise ValueError('NPC award plan was not fully allocated')

def create(db,owner,operation,rows,plan,guard):
    from els_server.domain.npc_exchange_rules import catalog,generic_indices
    if type(db)is not sqlite3.Connection or not db.in_transaction:raise ValueError('NPC source needs original writer')
    known=catalog()['recipes'];allowed={row['destination']for row in rows}
    if not rows or any(row not in known or row['index'] not in generic_indices() for row in rows):
        raise ValueError('NPC source original generic recipe identity')
    if any(row['template']not in allowed or row['template']in catalog()['blocked_new_outputs']for row in plan):
        raise ValueError('NPC award outside registered recipe')
    return _Source(_SEAL,db,owner,operation,rows,plan,guard)

def validate_source(source):
    if type(source)is not _Source:raise ValueError('Untrusted NPC acquisition source')
    return source
