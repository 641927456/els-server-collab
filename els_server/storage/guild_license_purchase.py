"""Finite110845 guards layered onto the existing original EA/EB purchase.

Reader registration would otherwise make existing ShopItem rows purchasable.
Require a live caller fence and actual saved owner, both before and after
precommit encoding; ordinary unrelated purchases retain their old contract.
"""
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.guild_membership_state import snapshot


def context(db, owner, account_id, town, merchant, entries, guard):
    if not any(template == 110845 for template, count in entries):
        return False
    if (not db.in_transaction or not callable(guard) or type(account_id) is not int
            or account_id <= 0 or merchant != 10018 or town not in range(20000,20014)
            or dict(entries).get(110845) != 1):
        raise ValueError('Guild license requires normal Ariel/live owner context')
    guard()
    # This also rejects missing/mismatched ownership and corrupt saved guilds.
    snapshot(db, owner, account_id)
    return True


def new_purchase(db, owner, account_id, before):
    if snapshot(db, owner, account_id) is not None:
        raise ValueError('Guild member cannot buy a creation license')
    if any(item['template'] == 110845 for item in before):
        raise ValueError('Character already holds a guild creation license')


def precommit(events, guard):
    guard()
    for event in events:
        encode_event(event)
    guard()
    return events
