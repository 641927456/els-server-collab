"""Stateless normal9ED quote adapter for the separately guarded atomic consumer.

Snapshots are supplied by a caller; this layer cannot establish SQL ownership,
locks, affordability or replay identity. Those belong to the pending transaction.
Raw flag0 selects NormalMaterialItem and flag1 CashMaterialItem, as traced from
the original UI mode through event18258 and the9ED sender.
"""
from els_server.protocol.equipment_reforge_transfer_messages import request
from els_server.domain.inventory_items import validate_item
from els_server.domain.equipment_reforge_rules import DEFAULT
from els_server.domain.equipment_reforge_transfer_rules import quote_pair

RUNTIME_ENABLED = True
MATERIAL_MODE_BY_FLAG = {0: 'normal', 1: 'ticket'}


def quote_request(payload, source_snapshot, target_snapshot):
    source_uid, target_uid, raw_flag = request(payload)
    if raw_flag != 0:raise ValueError('Transfer ticket mode remains closed')
    source = validate_item(source_snapshot)
    target = validate_item(target_snapshot)
    if source['uid'] != source_uid or target['uid'] != target_uid:
        raise ValueError('Transfer quote snapshots do not match requested UIDs')
    source_state = source.get('reforge', DEFAULT)
    target_state = target.get('reforge', DEFAULT)
    return quote_pair(source['template'], source_state[0], target['template'],
                      target_state[0], MATERIAL_MODE_BY_FLAG[raw_flag])
