"""Existing ED stone products credit the native counter, never inert bag rows."""
from els_server.protocol.shop_messages import ed_purchase_request
PRODUCT=127030
SKUS=frozenset((1200127030,1500508121,1500508122,1500508123))
def requested(payload):return any(sku in SKUS for sku,n in ed_purchase_request(payload))
def context(s,event,sequence,updates):
    from els_server.domain.tenebros_capacity_flow import selected
    path,owner,account,guard=selected(s)
    if(not s.shop_test or not s.ed_catalog_loaded or event.performers not in((),(0,))
       or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
       or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Native ED resurrection purchase context')
    town=s.active_map
    def prepare(db,count):
        guard(db)
        if(not s.shop_test or not s.ed_catalog_loaded or db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(town,)):raise ValueError('Resurrection purchase actor changed')
        from els_server.storage.profession_state import require_owner
        from els_server.storage.item_actor import require_active_character
        require_owner(db,owner,account);require_active_character(db,owner)
        if count is not None:
            from els_server.protocol.known_resurrection import box_result
            ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
            if ed is None:raise ValueError('Resurrection purchase balance missing')
            # Original197 reads count into User+2DB0. The exact same consumer
            # already handles the current190556 ten-stone source.
            updates.extend(box_result(ed[0],count))
    return prepare
