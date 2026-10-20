"""Authenticated finite chip installation/tuning, before generic socket dispatch."""
import struct
from els_server.protocol.equipment_chip_messages import installation,tuning,install_ack,tuning_ack,reset_unavailable_ack

def current_lease(s):
    app=getattr(s,'application',None)
    if app is None:return True
    identity=getattr(s,'identity',None);account=getattr(s,'account',None)
    if not isinstance(identity,dict) or account is None:return False
    account_id=identity.get('id');uid=getattr(account,'uid',None);root=getattr(account,'root',None)
    return bool(s.role=='game' and not getattr(s,'released',False) and app.playing.get(account_id) is s
        and account_id==account.account_id and app.accounts.get(account_id) is root
        and root is not None and root.character_accounts.get(uid) is account
        and account.store is not None and account.store.uid==uid)


def handle(s,event,sequence):
    # The decoded reset request has an outstanding native BBD wait. Keep the
    # unqualified reset transaction closed, but return its real failure shape.
    if event.event_id==0x202 and event.kind==0xbbc and s.client_build=='dx11_260923':
        return [reset_unavailable_ack()]
    if event.event_id!=0x202 or not s.item_test or s.client_build!='dx11_260923':return None
    is_install=event.kind==0x6e7 and isinstance(event.payload,bytes) and len(event.payload)>=6 and struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]==15
    if not is_install and event.kind!=0xbb8:return None
    uid=0;ed=0;encode=install_ack if is_install else tuning_ack
    try:
        if not current_lease(s):raise ValueError('Obsolete chip lease')
        uid=installation(event.payload)[0] if is_install else tuning(event.payload)
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
            or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Chip session envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_chip import perform
        if not current_lease(s):raise ValueError('Obsolete chip lease')
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':chip-compat-v1:'+str(s.account.uid)+':'+str(sequence),install=is_install,account_id=s.account.account_id)
    except ValueError:return [encode(uid,ed,result=2005)]
