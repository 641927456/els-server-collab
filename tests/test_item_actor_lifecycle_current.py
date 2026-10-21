"""Only new lifecycle guard risks: pending/replay/restore/finalize/legacy/rollback."""
import sys,ast,copy,hashlib,json,sqlite3,struct,tempfile,time,unittest,uuid
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage import bank_state,bank_money,npc_sale,npc_trade,inventory_actions,inventory_management,bag_moves,wear_moves
from els_server.storage.character_selection import save
from els_server.storage.character_lifecycle import change,DAY
from els_server.storage.item_actor import require_active_character
from tests.test_bank_state import payload as bank_wire
from tests.test_bank_money_memberships import money_wire
from tests.test_npc_trade import buy_payload,back_payload,sale_payload
from tests.test_inventory_actions import split_wire,discard_wire
ROWS=[]

class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='item-actor-qualified-');self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'game.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.owner=1001;self.now=int(time.time());self.sid=str(uuid.uuid4())
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=1001');db.execute('UPDATE reward_balances SET ed=50000000 WHERE uid=1001')
  self.weapon=self.grant(30160);self.lock=self.grant(30160);self.sale=self.grant(60100);self.crystal=self.grant(701000,10);self.potion=self.grant(77420,10)
 def grant(self,t,q=1):
  with closing(sqlite3.connect(self.path))as db,db:
   db.execute('BEGIN IMMEDIATE');return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q)],1001)[0]
 def dump(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def schedule(self,at):
  save(self.path,1,[],[1001])
  with patch('els_server.storage.character_lifecycle.current_time',return_value=at):return change(self.path,1,1001,'schedule')
 def test_pending_new_replay_restore_and_finalized(self):
  p=self.path;o=1001;gear=self.weapon;pot=self.potion;c=self.crystal;sale=self.sale
  actions=[
   ('wear104',lambda new:wear_moves.move(p,struct.pack('>BiBiB',1,gear['slot'],9,9,0),o,account_id=1,session_id=self.sid,sequence=18 if new else 17)),
   ('bag104',lambda new:bag_moves.move_bag_items(p,struct.pack('>BiBiB',pot['group'],pot['slot'],pot['group'],35,0),o)),
   ('bank551',lambda new:bank_state.transfer(p,o,bank_wire((c['group'],c['slot']),(8,0),c,context=c['uid']),'bank-new'if new else'bank-old')),
   ('bank7D7',lambda new:bank_money.transfer(p,o,money_wire(True,100),'money-new'if new else'money-old')),
   ('lock663',lambda new:inventory_management.lock_item(p,o,struct.pack('>QhiB',self.lock['uid'],1,0,0),'lock-new'if new else'lock-old')),
   ('discard109',lambda new:inventory_actions.discard(p,o,discard_wire(pot['uid'],1),'discard-new'if new else'discard-old')),
   ('split555',lambda new:inventory_actions.split_stack(p,o,split_wire(35,34,2,group=pot['group']),'split-new'if new else'split-old')),
   ('purchaseEA',lambda new:npc_trade.purchase(p,o,20002,buy_payload(),'buy-new'if new else'buy-old')),
   ('saleEC',lambda new:npc_sale.sell(p,o,sale_payload([(sale['uid'],1)]),'sell-new'if new else'sell-old','owned-history')),
   ('buyback567',lambda new:npc_trade.repurchase(p,o,back_payload(sale),'back-new'if new else'back-old','owned-history',20002)),
   ('bank372',lambda new:bank_state.sort(p,o,struct.pack('>i',8),'banksort-new'if new else'banksort-old')),
   ('bank475',lambda new:bank_state.expand(p,o,8,b'','expand-new'if new else'expand-old',self.expand_quote)),
   ('inventoryBD6',lambda new:inventory_management.sort_inventory(p,o,b'','sort-new'if new else'sort-old')),
   ('inventory370',lambda new:inventory_management.sort_category_inventory(p,o,struct.pack('>i',6),'category-new'if new else'category-old'))]
  self.expand_quote=bank_state.quote(p,o,8)
  for label,fn in actions:fn(False);ROWS.append(dict(label=label,stage='active-valid',passed=True))
  # A new encoder failure after charge/grant must still roll back every row.
  before=self.dump()
  with patch.object(npc_trade,'purchase_ack',side_effect=ValueError('owned injected encoder failure')):
   with self.assertRaisesRegex(ValueError,'owned injected encoder failure'):npc_trade.purchase(p,o,20002,buy_payload(),'encoder-failure')
  self.assertEqual(self.dump(),before);ROWS.append(dict(label='encoder-after-charge-and-grant',stage='active-rollback',passed=True))
  self.schedule(self.now)
  for stage in ('pending','finalized'):
   if stage=='finalized':
    # Restore through original waiting-period storage contract, then reuse only
    # committed operation ids. No encrypted frame is replayed or sequence weakened.
    with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+DAY+1):change(p,1,o,'restore')
    before=self.dump()
    for label,fn in actions:
     if label=='bag104':continue # 104 bag moves have no receipt; each is a new operation.
     fn(False);self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage='restored-committed-receipt-no-duplicate',passed=True))
    cold=LocalAccount(LocalState(p));cold.enable_characters()
    with closing(sqlite3.connect(p))as db:self.assertEqual(cold.get_inventory_snapshot()['items'],load_items(db,1001));self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    ROWS.append(dict(label='restored-cold-owned-inventory-and-FK',stage='cold',passed=True))
    self.schedule(self.now+2*DAY+2)
    with patch('els_server.storage.character_lifecycle.current_time',return_value=self.now+5*DAY+3):change(p,1,o,'finalize')
   for label,fn in actions:
    for new in (False,True)if label!='bag104'else(True,):
     before=self.dump()
     with self.assertRaisesRegex(ValueError,'Item actor is pending deletion or finalized'):fn(new)
     self.assertEqual(self.dump(),before);ROWS.append(dict(label=label,stage=stage,operation='new'if new else'committed-receipt',passed=True))
 def test_legacy_without_lifecycle_and_without_characters(self):
  path=Path(self.tmp.name)/'legacy.sqlite3';state=LocalState(path);account=LocalAccount(state);account.enable_inventory()
  with closing(sqlite3.connect(path))as db,db:
   # Existing single-role schema prior to Characters.enable; no lifecycle
   # creation/drop/rewriting is used to manufacture a compatibility result.
   missing=db.execute("SELECT 1 FROM sqlite_master WHERE name='character_lifecycle'").fetchone()is None
   self.assertTrue(missing);db.execute('BEGIN IMMEDIATE');require_active_character(db,1001)
   item=grant_items(db,[dict(template=77420,metadata=VERIFIED_TEMPLATES[77420],group=TEMPLATE_BAG_GROUPS[77420],quantity=3)],1001)[0]
  inventory_actions.discard(path,1001,discard_wire(item['uid'],1),'legacy-valid')
  with closing(sqlite3.connect(path))as db:self.assertEqual(next(i['count']for i in load_items(db,1001)if i['uid']==item['uid']),2)
  ROWS.append(dict(label='original-legacy-without-lifecycle',stage='legacy',passed=True))


if __name__=='__main__':unittest.main()
