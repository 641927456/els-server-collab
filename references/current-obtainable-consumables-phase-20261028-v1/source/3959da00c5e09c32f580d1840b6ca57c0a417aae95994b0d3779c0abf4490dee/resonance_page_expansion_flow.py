"""Only the held current712413 original219 route; no shop or grant additions."""
from contextlib import closing
import sqlite3
from els_server.protocol.career_messages import use_request,use_ack

def handle(s,event,sequence):
    if(event.event_id!=0x202 or event.kind!=0x219 or s.client_build!='dx11_260923'or not s.item_test):return None
    from els_server.domain.tenebros_capacity_flow import selected
    from els_server.domain.equipment_chip_flow import reset_context
    from els_server.storage.resonance_page_expansion import TEMPLATE,perform
    try:source_uid=use_request(event.payload);path,owner,account_id,prepare=selected(s)
    except(ValueError,AttributeError):return None
    operation='owned-erp-page-v1:'+s.shop_session_id+':'+str(account_id)+':'+str(owner)+':'+str(sequence)
    with closing(sqlite3.connect(path))as db:
        source=db.execute('SELECT template FROM inventory_items WHERE owner=?AND uid=?',(owner,source_uid)).fetchone()
        historical=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='inventory_action_receipts'").fetchone()and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?AND owner=?',(operation,owner)).fetchone())
    if source!=(TEMPLATE,)and not historical:return None
    try:
        reset_context(s,event,sequence)
        def guard(db):reset_context(s,event,sequence);prepare(db)
        result=perform(path,owner,account_id,event.payload,operation,prepare=guard)
        if result is None:raise ValueError('ERP expansion source no longer current')
        s.resonance_page_sync_key=(account_id,owner,result['legacy_revision'],(result['page_revision'],))
        return result['events']
    except(ValueError,OverflowError):return [use_ack(result=-1)]
