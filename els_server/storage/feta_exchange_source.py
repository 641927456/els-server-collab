"""One live exact SQL debit capability for the two otherwise closed products."""
from pathlib import Path
import hashlib
from els_server.domain.feta_exchange_rules import request,_FetaAuthority

class _FetaSource:
 def __init__(self,db,owner,account,authority,operation,payload):
  if type(authority)is not _FetaAuthority:raise ValueError('Feta source authority type')
  self.db,self.owner,self.account,self.authority=db,owner,account,authority
  self.operation,self.payload=operation,payload;self.row=request(payload);self.phase='captured'
  if self.row['index']not in(688,689,690):raise ValueError('Feta source finite private products')
  self.savepoint='feta_source_'+hashlib.sha256(operation.encode()).hexdigest()
  db.execute('SAVEPOINT '+self.savepoint);self._check();self.before=self._rows()
  self.expected=None;self.write_mark=None
 def _rows(self):return tuple(tuple(r)for r in self.db.execute('SELECT uid,owner,template,metadata,count,bag_group,slot FROM inventory_items WHERE owner=?ORDER BY uid',(self.owner,)))
 def _check(self):
  from els_server.storage.feta_exchange import _context
  if self.phase=='closed'or self.authority.operation!=self.operation or self.authority.payload!=self.payload or request(self.payload)!=self.row:raise ValueError('Feta source identity')
  _context(self.db,self.owner,self.account,self.authority)
  from els_server.storage.feta_exchange_weekly import receipt
  receipt(self.db,self.account,self.owner,self.row,self.operation)
  # Committing or rolling back invalidates this marker; never recreate on failure.
  self.db.execute('RELEASE SAVEPOINT '+self.savepoint);self.db.execute('SAVEPOINT '+self.savepoint)
 def debit_complete(self,debits):
  self._check()
  if self.phase!='captured'or type(debits)is not list or not debits:raise ValueError('Feta source debit phase')
  expected={r[0]:r for r in self.before};seen=set();total=0
  for uid,take in debits:
   r=expected.get(uid)
   if(type(uid)is not int or type(take)is not int or uid in seen or r is None or r[1:4]!=(self.owner,119317,2)or r[5]!=3 or not 1<=take<=r[4]<=1000):raise ValueError('Feta source debit rows')
   seen.add(uid);total+=take
   if take==r[4]:del expected[uid]
   else:expected[uid]=r[:4]+(r[4]-take,)+r[5:]
  self.expected=tuple(expected[u]for u in sorted(expected))
  if total!=self.row['source_quantity']or self._rows()!=self.expected:raise ValueError('Feta exact SQL debit mismatch')
  self.write_mark=self.db.total_changes;self.phase='debited'
 def _plan(self,plan):
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
  t=self.row['destination'];expected=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=self.row['destination_quantity'])]
  if type(plan)is not list or plan!=expected or any(type(v)is not int for p in plan for v in p.values()):raise ValueError('Feta exact complete private plan')
 def bind_factory(self,db,owner,plan):
  self._check();self._plan(plan)
  if self.phase!='debited'or db is not self.db or owner!=self.owner or self.db.total_changes!=self.write_mark or self._rows()!=self.expected:raise ValueError('Feta factory source context/reuse')
  self.phase='factory'
 def validate_plan(self,plan):
  self._check();self._plan(plan)
  if self.phase!='factory'or self.db.total_changes!=self.write_mark or self._rows()!=self.expected:raise ValueError('Feta factory plan phase')
 def consume_template(self,template):
  self._check()
  if template!=self.row['destination']or template not in(119216,119328,30880):raise ValueError('Feta source substituted output')
  self.validate_plan([dict(template=template,metadata=2,group=3 if template==119216 else 4,quantity=self.row['destination_quantity'])]);self.phase='spent'
  return True
 def close(self):
  if self.phase!='closed':self.phase='closed';self.db.execute('RELEASE SAVEPOINT '+self.savepoint)
 def can_stack(self,item,plan):
  self._check()
  if self.phase!='spent':raise ValueError('Feta factory merge phase')
  return set(item)=={'uid','template','metadata','count','group','slot'}and item['template']==self.row['destination']

def validate_source(source):
 if type(source)is not _FetaSource:raise ValueError('Feta exact internal source required')
 return source
