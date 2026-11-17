"""Bind each market request to its current character and loaded town."""
from els_server.domain.option_conversion_existing_flow import _session, _selected_authorizer
from els_server.storage.local_state import TOWN_SCENES

# House 40028 / NPC 10025 exposes NCBT_TRADE_BOARD (47) in these
# supported DLG_Map_House common scenes or DLG_Map_Village house lists.
BOARD_SCENES = frozenset((
    258, 262, 263, 265, 268, 326, 417, 491, 497, 512, 517, 534, 582,
    606, 636, 637, 725, 778, 788, 851, 894, 964, 1004, 1023, 1131, 1214,
))


class TradeBoardAuthority:
    __slots__ = ('session', 'path', 'owner', 'account_id', 'kind', '_selected', '_location')

    def __init__(self, session, event, sequence):
        if (event.event_id != 0x202
                or event.kind not in (0x9fc, 0x9fe, 0xa00, 0xa02, 0xa04, 0xa06, 0xa08,
                                      0xa0a, 0xa0c, 0xa11, 0xa13, 0xa18)
                or session.client_build != 'dx11_260923'
                or type(sequence) is not int or not 0 < sequence < 2**32
                or event.performers not in ((), (0,))
                or event.uid != 2**64-1 or event.target_uid != 2**64-1
                or event.payload_mode != 0):
            raise ValueError('TradeBoard original purchase envelope')
        selection = _session(session)
        self.session, self.kind = session, event.kind
        self.path, self.owner, self.account_id = selection
        self._selected = _selected_authorizer(session, selection)
        location = session.account.get_location()
        self._location = (location['map'], location['board'])

    def check(self, db, now):
        session = self.session
        town, board = self._location
        if (not self._selected() or TOWN_SCENES.get(town) not in BOARD_SCENES
                or session.active_map != town or session.pending_map != town
                or session.dungeon_return_pending
                or getattr(session, 'town_warp_transition', None) is not None):
            raise ValueError('TradeBoard requires a loaded market town')
        location = session.account.get_location()
        if (location['map'], location['board']) != (town, board) or db.execute(
                'SELECT town,board FROM location WHERE uid=?', (self.owner,)
        ).fetchone() != (town, board):
            raise ValueError('TradeBoard town or line changed')
