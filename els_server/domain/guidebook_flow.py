"""Keep native first-use tutorials read across reconnects and character changes."""
from els_server.protocol import guidebook_messages as wire
from els_server.storage import guidebook as storage
from els_server.domain.equipment_chip_flow import current_lease


def require_actor(session):
    account=session.account
    if (session.client_build!='dx11_260923' or session.role!='game' or not session.enter_town
            or session.phase not in ('player_initialized','skill_ui_ready','initialization_confirmed',
                'map_loading','square_accepted','town_ready','dungeon_loading','dungeon_active')
            or account.characters is None or account.store is None
            or account.store.uid!=account.uid or not current_lease(session)):
        raise ValueError('Guidebook requires the current selected character')


def initialization(session):
    require_actor(session)
    return wire.initialization(storage.load(session.account.store,session.account.account_id))


def handle(session,event):
    if event.kind not in (0x810,0x812):return None
    require_actor(session)
    if (event.event_id!=0x202 or event.performers not in ((),(0,))
            or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):
        raise ValueError('Invalid guidebook envelope')
    if event.kind==0x810:
        if event.payload:raise ValueError('Guidebook query has no body')
        return [initialization(session)]
    flags=wire.request(event.payload)
    storage.save(session.account.store,session.account.account_id,flags)
    return []  # 812 is the native whole-map upload, with no invented ACK.
