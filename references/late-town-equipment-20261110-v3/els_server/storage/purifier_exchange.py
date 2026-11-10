"""Original purifier selection using the shared deterministic material writer."""
from els_server.protocol.purifier_exchange_messages import request,acknowledgement
from els_server.domain.purifier_exchange_rules import ACCESSORY_BOXES,recipe
from els_server.storage.material_exchange import exchange as commit

def exchange(path,owner,town,payload,operation,*,account_id,now=None,guard=lambda db:None):
 r=request(payload);rule=recipe(r)
 if town!=20013:raise ValueError('Purifier exchange requires the current NPC town')
 def issue(db,owner,operation,plan,validate):
  from els_server.domain.raid_reward_items import _issue_source
  def authorize(writer):
   validate()
   return True
  return _issue_source(db,owner,operation,'npc_trade',
   dict(house=r.house,source=r.source,source_quantity=r.source_quantity,destination=r.destination),
   plan,authorize)
 return commit(path,owner,town,payload,operation,r,account_id=account_id,source_quantity=rule['source_quantity'],
               destination=r.destination,output_quantity=1,acknowledgement=acknowledgement,
               guard=guard,now=now,source_factory=issue if r.destination in ACCESSORY_BOXES else None)
