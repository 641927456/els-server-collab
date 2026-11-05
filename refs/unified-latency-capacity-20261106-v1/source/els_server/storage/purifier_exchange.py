"""Original purifier selection using the shared deterministic material writer."""
from els_server.protocol.purifier_exchange_messages import request,acknowledgement
from els_server.domain.purifier_exchange_rules import recipe
from els_server.storage.material_exchange import exchange as commit
def exchange(path,owner,town,payload,operation,*,account_id,now=None):
 r=request(payload);rule=recipe(r)
 if town!=20013:raise ValueError('Purifier exchange requires the current NPC town')
 return commit(path,owner,town,payload,operation,r,account_id=account_id,source_quantity=rule['source_quantity'],destination=r.destination,output_quantity=1,acknowledgement=acknowledgement,guard=lambda db:None,now=now)
