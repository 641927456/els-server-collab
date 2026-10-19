"""Authenticated finite chip installation/tuning, before generic socket dispatch."""
import struct
from els_server.protocol.equipment_chip_messages import installation,tuning,install_ack,tuning_ack

def handle(s,event,sequence):
    if event.event_id!=0x202 or not s.item_test or s.client_build!='dx11_260923':return None
    is_install=event.kind==0x6e7 and isinstance(event.payload,bytes) and len(event.payload)>=6 and struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]==15
    if not is_install and event.kind!=0xbb8:return None
    uid=0;ed=0;encode=install_ack if is_install else tuning_ack
    try:
        uid=installation(event.payload)[0] if is_install else tuning(event.payload)
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
            or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Chip session envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_chip import perform
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':chip-compat-v1:'+str(s.account.uid)+':'+str(sequence),install=is_install)
    except ValueError:return [encode(uid,ed,result=2005)]
