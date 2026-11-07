"""Authenticated dedicated engraving dispatch before generic socket modes."""
import struct
from els_server.protocol.equipment_engrave_messages import request,acknowledge

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
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    if not isinstance(event.payload,bytes) or len(event.payload)<6:return None
    mode=struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]
    if mode not in (5,6):return None
    uid=0;ed=0
    try:
        if not current_lease(s):raise ValueError('Obsolete engraving lease')
        uid=request(event.payload)[0]
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Engraving session envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_engrave import perform
        if not current_lease(s):raise ValueError('Obsolete engraving lease')
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':engrave-compat-v1:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
    except ValueError:return [acknowledge(uid,ed,mode=mode,result=2005)]
