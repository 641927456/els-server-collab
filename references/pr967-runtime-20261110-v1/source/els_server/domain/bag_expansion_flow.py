"""Connect the native inventory expansion popup to existing bag allowances."""
from contextlib import closing
import os
import sqlite3
import time
import traceback
from els_server.protocol import bag_expansion_messages as wire
from els_server.domain.equipment_chip_flow import current_lease

# TEMPORARY diagnostics: state/ is gitignored. Remove before committing.
_DEBUG=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'state','bag-expansion-debug.log')
def _dbg(text):
    try:
        with open(_DEBUG,'a',encoding='utf-8') as handle:handle.write(time.strftime('%H:%M:%S ')+text+'\n')
    except Exception:pass


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x47b,0x479) or s.client_build!='dx11_260923':return None
    quote=event.kind==0x47b
    failure=wire.quote_ack if quote else wire.expansion_ack
    account=s.account;store=account.store;uid=account.uid;account_id=account.account_id;session=s.shop_session_id
    def prepare(db):
        if (not s.item_test or s.role!='game' or s.phase!='town_ready' or not current_lease(s)
            or getattr(s,'released',False) or s.account is not account or account.store is not store
            or store is None or store.uid!=uid or (account.uid,account.account_id,s.shop_session_id)!=(uid,account_id,session)
            or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers not in ((),(0,)) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Bag expansion selected actor/context')
    try:
        _dbg('recv kind=%#x seq=%r payload=%s'%(event.kind,sequence,event.payload.hex() if isinstance(event.payload,bytes) else event.payload))
        prepare(None);group=wire.request(event.payload)
        _dbg('group=%r quote=%r'%(group,quote))
        key=(uid,group)
        if not hasattr(s,'bag_expansion_quotes'):s.bag_expansion_quotes={}
        from els_server.storage.bag_capacity import expansion_quote,direct_expansion
        if quote:
            from els_server.storage.profession_state import require_owner
            from els_server.storage.item_actor import require_active_character
            from els_server.storage.bag_capacity import allowances
            with closing(sqlite3.connect(store.path,timeout=10)) as db:
                db.execute('BEGIN');require_owner(db,uid,account_id);require_active_character(db,uid)
                _dbg('capacities=%r'%(allowances(db,uid),))
                offer=expansion_quote(db,uid,group)
            _dbg('offer=%r'%(offer,))
            s.bag_expansion_quotes[key]=offer
            return [wire.quote_ack(offer[2])]
        operation=session+':bag-expand:'+str(uid)+':'+str(sequence)
        before=account.character()
        event=direct_expansion(store.path,uid,account_id,event.payload,operation,
            expected=s.bag_expansion_quotes.get(key),prepare=prepare)
        _dbg('purchased kind=%#x payload=%s'%(event.kind,event.payload.hex()))
        s.bag_expansion_quotes.pop(key,None)
        reply=[event]
        # The 47A consumer only updates ED/capacity state; the bag grid repaints
        # from the same 26C delta notice the ED shop purchase path already uses.
        # expansion_notice returns None on receipt replay, so no fake delta.
        from els_server.domain.bag_capacity import expansion_notice
        notice=expansion_notice(before,account.character())
        if notice is not None:reply.append(notice)
        return reply
    except ValueError:
        _dbg('REJECTED\n'+traceback.format_exc())
        return [failure(result=-1)]
