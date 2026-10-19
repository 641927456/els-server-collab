"""Authenticated town-only adapter for independently qualified ED/EP exchange."""
import sqlite3
from els_server.domain.ep_conversion import policy,Rate,ConversionResult,ConversionRejected
from els_server.protocol.ep_conversion_messages import acknowledgement,catalogue
from els_server.storage.ep_conversion import convert,wallet

def handle(session,event,sequence):
    if not (session.item_test and session.client_build=='dx11_260923' and event.event_id==0x202 and event.kind in (0xa69,0xa5c)):
        return None
    def failed(result,balances=(0,0)):
        return [catalogue(result=int(result)) if event.kind==0xa69 else acknowledgement(*balances,result=int(result))]
    valid=(session.role=='game' and session.phase=='town_ready' and session.account.store is not None
           and session.account.characters is not None and type(sequence) is int and 1<=sequence<2**32
           and event.performers==(0,) and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0)
    if not valid:return failed(ConversionResult.INVALID_STATE)
    try:
        path=session.account.store.path;uid=session.account.uid;account_id=session.account.account_id
        balances=wallet(path,account_id=account_id,uid=uid)
        if event.kind==0xa69:
            if event.payload:raise ConversionRejected(ConversionResult.UNKNOWN)
            rate=policy()
            if type(rate) is not Rate:raise ConversionRejected(ConversionResult.UNAVAILABLE)
            return [catalogue(rate)]
        operation=session.shop_session_id+':'+str(uid)+':ep-conversion:'+str(sequence)
        return [convert(path,event.payload,operation,account_id=account_id,uid=uid)]
    except (ValueError,sqlite3.Error) as error:
        # The failed transaction has rolled back. A fresh owned read cannot
        # disclose another role's wallet or restore a historical balance.
        try:current=wallet(path,account_id=account_id,uid=uid)
        except (ValueError,sqlite3.Error):current=(0,0)
        return failed(getattr(error,'result',ConversionResult.UNKNOWN),current)
