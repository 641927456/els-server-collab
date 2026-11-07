"""Material conservation/debit primitive inside the crafting transaction.

The transaction supplies an explicit allocation using its labelled compatibility
policy; this primitive never chooses output, UID priority or profession awards.
"""
from collections import Counter
from copy import deepcopy
from uuid import uuid4

from els_server.domain.manufacture_requirements import inventory_candidates, I32_MAX


def validate_allocation(items, demand, allocation, *, now):
    """Prove exact material conservation against current-schema candidates.

    Ownership belongs to the caller's inventory snapshot. This validates only
    quantities and known availability fields, not the unrepresented native
    flags or the meaning of selected/auxiliary UIDs.
    """
    if type(demand) is not dict or any(
        type(t) is not int or not 1 <= t <= I32_MAX or
        type(n) is not int or not 1 <= n <= I32_MAX for t, n in demand.items()
    ):
        raise ValueError('Invalid material demand')
    candidates = inventory_candidates(items, now=now)
    usable = {uid: (t, count) for t, entries in candidates.items() for uid, count in entries}
    originals = {i['uid']: i for i in items}
    if type(allocation) not in (list, tuple) or len(allocation) > len(usable):
        raise ValueError('Invalid allocation collection')
    seen, totals, changes = set(), Counter(), []
    for row in allocation:
        if (type(row) is not dict or set(row) != {'uid', 'quantity'} or
            type(row['uid']) is not int or not 1 <= row['uid'] < 2**63 or
            type(row['quantity']) is not int or not 1 <= row['quantity'] <= I32_MAX):
            raise ValueError('Invalid allocation row')
        uid, quantity = row['uid'], row['quantity']
        if uid in seen:
            raise ValueError('Duplicate allocation UID')
        seen.add(uid)
        if uid not in usable:
            raise ValueError('Unavailable allocation UID')
        template, count = usable[uid]
        if template not in demand or quantity > count:
            raise ValueError('Material mismatch or stack overdraft')
        totals[template] += quantity
        if totals[template] > demand[template]:
            raise ValueError('Material demand exceeded')
        before = deepcopy(originals[uid])
        after = deepcopy(before) if quantity < count else None
        if after is not None:
            after['count'] -= quantity
        changes.append(dict(before=before, after=after, quantity=quantity))
    if dict(totals) != demand:
        raise ValueError('Material demand not satisfied exactly')
    return changes


def apply_debits(db, owner, account_id, demand, allocation, *, now):
    """Apply a caller-supplied allocation inside an existing SQL transaction.

    Never commits or creates tables. An internal savepoint rolls back this
    entire debit on failure, even if the caller catches the error and commits.
    The outer transaction MUST also perform verified fees, outputs, growth,
    response encoding and receipts before committing. Calling this primitive
    alone is not authorized crafting and provides no retry/idempotency policy.
    """
    from els_server.storage.profession_state import snapshot
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import remove
    if not db.in_transaction:
        raise ValueError('Material debit requires outer transaction')
    savepoint = 'manufacture_debit_' + uuid4().hex
    db.execute('SAVEPOINT ' + savepoint)
    try:
        snapshot(db, owner, account_id)  # authenticates owner before touching sidecars
        items = load_items(db, owner)
        changes = validate_allocation(items, demand, allocation, now=now)
        for change in changes:
            before, after = change['before'], change['after']
            if after is None:
                remove(db, owner, before)
            else:
                updated = db.execute(
                    'UPDATE inventory_items SET count=? WHERE owner=? AND uid=? AND count=?',
                    (after['count'], owner, before['uid'], before['count']))
                if updated.rowcount != 1:
                    raise ValueError('Material stack changed during debit')
        load_items(db, owner)
        db.execute('RELEASE ' + savepoint)
        return changes
    except BaseException:
        db.execute('ROLLBACK TO ' + savepoint)
        db.execute('RELEASE ' + savepoint)
        raise
