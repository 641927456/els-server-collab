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
    # User-local existing-inventory reset; other chip paths retain their semantics.
    if event.event_id==0x202 and event.kind==0xbbc and s.client_build=='dx11_260923':
        return handle_reset(s,event,sequence)
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

def reset_authority(s):
    from els_server.storage.read_scope import checked_paths
    with checked_paths() as resolve:
        from uuid import UUID
        from els_server.application import Application,FriendsSession
        from els_server.domain.local_session import LocalAccount,LocalSession
        from els_server.domain.roster_account import RosterAccount
        from els_server.storage.local_state import LocalState
        from els_server.storage.characters import Characters
        from els_server.storage.accounts import Accounts
        account=getattr(s,'account',None);root=getattr(account,'root',None)
        if (type(account) is not LocalAccount or type(root) not in (LocalAccount,RosterAccount)
            or root.root is not root or root.character_accounts.get(account.uid) is not account
            or type(account.store) is not LocalState or account.store.uid!=account.uid
            or type(account.characters) is not Characters or root.characters is not account.characters
            or account.account_id!=root.account_id or account.characters.account_id!=account.account_id):
            raise ValueError('Chip reset current actor graph')
        path=resolve(account.store.path)
        if resolve(account.characters.path)!=path:
            raise ValueError('Chip reset character save binding')
        if type(root) is RosterAccount:
            if resolve(root.path)!=path:raise ValueError('Chip reset roster save binding')
        elif type(root.store) is not LocalState or root.store.uid!=root.uid or resolve(root.store.path)!=path:
            raise ValueError('Chip reset root save binding')
        app=getattr(s,'application',None)
        if app is not None:
            identity=getattr(s,'identity',None)
            if (type(s) is not FriendsSession or type(app) is not Application
                or app.config.mode!='friends' or type(identity) is not dict
                or type(identity.get('id')) is not int or identity['id']!=account.account_id
                or type(app.registry) is not Accounts or not current_lease(s)
                or resolve(app.config.state_file)!=path
                or resolve(app.config.accounts_file)!=resolve(app.registry.path)
                or not app.registry.enabled(identity['id'])):
                raise ValueError('Chip reset trusted friends actor')
        else:
            app=getattr(s,'_chip_reset_local_application',None)
            if (type(s) is not LocalSession or type(app) is not Application
                or getattr(s,'_chip_reset_local_live',None) is not True
                or app.config.mode!='local' or type(root) is not LocalAccount
                or app.account is not root or root.account_id!=1
                or resolve(app.config.state_file)!=path):
                raise ValueError('Chip reset trusted local actor')
        token=s.shop_session_id
        if type(token) is not str or str(UUID(token))!=token or UUID(token).version!=4:
            raise ValueError('Chip reset session token')


def reset_context(s,event,sequence):
    reset_authority(s)
    if (not s.item_test or s.role!='game' or s.phase!='town_ready'
        or s.account.characters is None or s.account.store is None
        or s.account.store.uid!=s.account.uid or not {0x28,0x225,0x227}<=s.completed
        or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
        or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
        raise ValueError('Chip reset current context')


def handle_reset(s,event,sequence):
    try:
        reset_context(s,event,sequence)
        from pathlib import Path
        from els_server.storage.equipment_chip_reset import perform
        account=s.account;store=account.store;root=account.root
        owner=account.uid;account_id=account.account_id;session_id=s.shop_session_id
        local_app=getattr(s,'_chip_reset_local_application',None)
        app=getattr(s,'application',None);identity=getattr(s,'identity',None)
        registry=getattr(app,'registry',None)
        path=Path(store.path).resolve()
        def prepare(db):
            reset_context(s,event,sequence)
            if (s.account is not account or account.store is not store or account.root is not root
                or getattr(s,'_chip_reset_local_application',None) is not local_app
                or getattr(s,'application',None) is not app or getattr(s,'identity',None) is not identity
                or getattr(app,'registry',None) is not registry
                or (account.uid,account.account_id,s.shop_session_id)!=(owner,account_id,session_id)
                or Path(store.path).resolve()!=path):
                raise ValueError('Chip reset selected actor changed')
        operation=session_id+':chip-reset-local-v1:'+str(owner)+':'+str(sequence)
        return perform(path,owner,account_id,event.payload,operation,prepare=prepare)
    except ValueError:
        return [reset_unavailable_ack()]
