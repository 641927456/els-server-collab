"""Native paid17 for existing complete weapon29; normal selected actor authority only.

The shared reset_authority call below verifies identity graph/save/UUID/live lease;
it does not invoke a Chip/reset handler, quota, coupon, result or permission.
"""
import struct
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol.option_conversion_existing_messages import request,acknowledgement


def _session(s):
    from pathlib import Path
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    if (not current_lease(s) or getattr(s,'released',False)
        or s.role!='game' or s.phase!='town_ready' or not s.item_test
        or s.client_build!='dx11_260923' or s.account.characters is None
        or s.account.store is None or s.account.store.uid!=s.account.uid
        or not {0x28,0x225,0x227}<=s.completed):
        raise ValueError('Conversion current selected town actor required')
    return Path(s.account.store.path).resolve(),s.account.uid,s.account.account_id


def _selected_authorizer(s,selection):
    account=s.account;store=account.store;root=getattr(account,'root',None)
    characters=account.characters;identity=getattr(s,'identity',None)
    operation_root=s.shop_session_id;app=getattr(s,'application',None)
    local_app=getattr(s,'_chip_reset_local_application',None)
    def authorize():
        try:
            return (s.account is account and s.account.store is store
                and s.account.characters is characters and getattr(s.account,'root',None)is root
                and getattr(s,'identity',None)is identity and s.shop_session_id==operation_root
                and getattr(s,'application',None)is app
                and getattr(s,'_chip_reset_local_application',None)is local_app
                and _session(s)==selection)
        except (ValueError,AttributeError,TypeError):return False
    return authorize


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    if not isinstance(event.payload,bytes)or len(event.payload)<6 or struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]!=17:return None
    uid=0;ed=0
    try:
        selection=_session(s);path,owner,account_id=selection
        authorize=_selected_authorizer(s,selection)
        if (type(sequence)is not int or not 1<=sequence<2**32
            or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
            or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Conversion session/envelope')
        ed=s.account.get_reward_balances()['ed'];uid=request(event.payload)
        from els_server.storage.option_conversion_existing import perform
        return perform(path,owner,event.payload,s.shop_session_id+':existing-paid17-v1:'+str(owner)+':'+str(sequence),account_id=account_id,authorize=authorize)
    except ValueError:return [acknowledgement(uid,ed,result=2005)]
