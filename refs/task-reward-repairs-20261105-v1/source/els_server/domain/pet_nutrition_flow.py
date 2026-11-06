"""The current pet-information UI's original nutrient and digestive requests."""
import sqlite3
from els_server.protocol import pet_progression_messages as wire

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x8ad,0x8b9)or s.client_build!='dx11_260923':return None
    failure=wire.nutrient if event.kind==0x8ad else wire.digestion
    try:
        from els_server.domain.housing_access_flow import capture
        same,guard=capture(s)
        if(event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Pet nutrient original envelope')
        from els_server.storage.pet_nutrition import perform
        operation=s.shop_session_id+':pet-nutrient:'+str(s.account.uid)+':'+str(sequence)
        return perform(s.account.store.path,s.account.uid,s.account.account_id,event.kind,event.payload,operation,guard)
    except(ValueError,sqlite3.Error,OverflowError,AttributeError):
        if'same'in locals()and not same():return[]
        return[failure(result=-1)]
