"""One admitted account wishlist template through the original native UI."""
import sqlite3
from els_server.domain.equipment_chip_flow import current_lease
from els_server.protocol import shop_messages as wire
from els_server.storage import wishlist_state as store


def handle(session,event):
    query=event.kind==0x1f1
    def failed():return [wire.empty_cart_ack() if query else wire.wish_list_unavailable_ack()]
    a=session.account
    if (session.client_build!='dx11_260923' or session.role!='game'
            or session.phase!='town_ready' or a.store is None or a.characters is None
            or a.store.uid!=a.uid or not current_lease(session)):
        return failed()
    try:
        if query:
            if event.payload:raise ValueError('Wishlist query body must be empty')
            return store.snapshot(a.store.path,a.account_id,a.uid,lambda rows:[wire.wishlist_query_ack(rows)])
        items,delete=wire.wishlist_modify_request(event.payload)
        return store.modify(a.store.path,a.account_id,a.uid,items,delete,
                            lambda rows,delete:[wire.wishlist_modify_ack(rows,delete)])
    except (ValueError,OverflowError,sqlite3.OperationalError):
        return failed()
