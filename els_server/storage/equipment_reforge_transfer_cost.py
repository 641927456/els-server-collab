"""Read current owner-scoped transfer expenses inside the caller's transaction.

This is a pending transaction component, not a transfer operation. It writes no
SQL and supplies no permission for a later transaction: the final transfer must
reload/revalidate under its own BEGIN IMMEDIATE, apply the independently proved
state transition and costs, encode the full response and commit one receipt.
Each ownlife retention belongs to the explicit nonretail compatibility policy;
this unchanged cost reader never chooses resulting life or applies debits.
"""
from dataclasses import dataclass

from els_server.domain.equipment_reforge_transfer_preflight import quote_request
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.equipment_reforge_transfer_messages import request
from els_server.storage.equipment_reforge import allocation, require_item
from els_server.storage.inventory_state import load_items
from els_server.storage.manufacture_debits import validate_allocation
from els_server.storage.npc_trade import balances
from els_server.storage.profession_state import require_owner

RUNTIME_ENABLED = True


@dataclass(frozen=True)
class OwnedTransferCost:
    source_uid: int
    target_uid: int
    ed_before: int
    balance_revision: int
    ed_fee: int
    materials: tuple[tuple[int, int], ...]
    debits: tuple[tuple[int, int], ...]


def read_owned_cost(db, owner, account_id, payload, *, now):
    """Validate SQL identities, finite normal materials and exact allocation.

    UID order is the existing server's compatibility allocation policy, not a
    recovered native selection rule. Flag1 remains rejected while ticket118254
    lacks finite item admission. Reading a quote never consumes anything.
    """
    if not db.in_transaction:
        raise ValueError('Transfer cost requires caller transaction')
    if type(now) is not int or now < 0:
        raise ValueError('Transfer cost clock')
    source_uid, target_uid, _ = request(payload)
    require_owner(db, owner, account_id)
    items = load_items(db, owner)
    by_uid = {item['uid']: item for item in items}
    source, target = by_uid.get(source_uid), by_uid.get(target_uid)
    require_item(source, equipment=True, now=now)
    require_item(target, equipment=True, now=now)
    quote = quote_request(payload, source, target)
    demand = dict(quote.materials)
    if any(template not in VERIFIED_TEMPLATES for template in demand):
        raise ValueError('Transfer cost includes unadmitted material')
    balance = balances(db, owner)
    if quote.ed > balance['ed'] or balance['revision'] >= 2**63 - 1:
        raise ValueError('Transfer cost ED/revision bound')
    debits = allocation(items, demand, now)
    validate_allocation(items, demand, debits, now=now)
    return OwnedTransferCost(source_uid, target_uid, balance['ed'],
                             balance['revision'], quote.ed, quote.materials,
                             tuple((row['uid'], row['quantity']) for row in debits))
