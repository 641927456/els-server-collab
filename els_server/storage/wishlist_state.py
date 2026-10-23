"""Finite account wishlist; no purchase, currency or inventory mutation."""
import functools
import sqlite3
from contextlib import closing
from els_server.storage.bank_state import account_for
from els_server.storage.item_actor import require_active_character
from els_server.storage.character_schema import stored_character_type

TEMPLATE=723522
SKU=1200723522
DDL='''CREATE TABLE IF NOT EXISTS account_wishlist_items (
    account_id INTEGER NOT NULL CHECK(account_id>0),
    template INTEGER NOT NULL CHECK(template=723522),
    PRIMARY KEY(account_id,template))'''


@functools.lru_cache(maxsize=1)
def admitted():
    # Reuse the installed source-owned manifest/record guards, not a second
    # client record or a new billing product table. This is a local ED offer.
    from els_server.domain.fashion_singles import definitions
    from els_server.domain.acquisition_policy import require_acquirable
    from els_server.domain.shop_listing import ice_equipment
    row=next((r for r in definitions() if r['template']==TEMPLATE),None)
    if (row is None or row['sku']!=SKU or row['role']!=1
            or row['category']!=16 or row['price']!=50 or row['quantity']!=1):
        raise ValueError('Wishlist source offer mismatch')
    require_acquirable(TEMPLATE)
    if TEMPLATE in ice_equipment():raise ValueError('Wishlist offer is excluded')
    return frozenset((TEMPLATE,))


@functools.lru_cache(maxsize=15)
def _visible_templates(unit):
    # This single, source-owned non-stackable fashion row enters the installed
    # ED catalog through fashion_singles.offers(unit), can_acquire and the ice
    # exclusion. Reuse their caches; do not rebuild thousands of unrelated SKUs.
    return admitted() if unit==1 else frozenset()


def _owner(db,account,uid):
    if type(account) is not int or not 1<=account<2**63:
        raise ValueError('Wishlist account identity')
    require_active_character(db,uid)
    if account_for(db,uid)!=account:raise ValueError('Wishlist actor ownership')


def _items(db,account):
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_wishlist_items'").fetchone()
    if not exists:return ()
    rows=tuple(r[0] for r in db.execute('SELECT template FROM account_wishlist_items WHERE account_id=? ORDER BY template',(account,)))
    if len(rows)>1 or any(type(t) is not int or t!=TEMPLATE for t in rows):
        raise ValueError('Wishlist persisted finite scope')
    return rows


def snapshot(path,account,uid,encode):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN')
        _owner(db,account,uid)
        visible=_visible_templates(stored_character_type(db,uid))
        return encode(tuple(t for t in _items(db,account) if t in visible))


def modify(path,account,uid,items,delete,encode):
    items=tuple(items)
    if items!=(TEMPLATE,) or type(delete) is not bool:
        raise ValueError('Wishlist template is not admitted')
    if TEMPLATE not in admitted():raise ValueError('Wishlist source unavailable')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        _owner(db,account,uid)
        if TEMPLATE not in _visible_templates(stored_character_type(db,uid)):
            raise ValueError('Wishlist item is not in this character catalog')
        before=_items(db,account)
        if delete and before:
            db.execute('DELETE FROM account_wishlist_items WHERE account_id=? AND template=?',(account,TEMPLATE))
        elif not delete and not before:
            db.execute(DDL)
            db.execute('INSERT INTO account_wishlist_items VALUES (?,?)',(account,TEMPLATE))
        # Echo the affected template even when unchanged: the native delete
        # consumer needs the removed ID, not the post-delete empty set.
        # Encoding remains within the transaction, including first-use DDL.
        return encode(items,delete)
