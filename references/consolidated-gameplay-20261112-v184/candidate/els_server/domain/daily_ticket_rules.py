"""Native daily free entries and owned extra-entry tickets, without new pools."""
import functools
from els_server.game_data import client_data
from els_server.domain import aurora_ticket_rules as aurora

GIANTS = (34310, 34360, 34730, 35110)
ELRIANODE = {
    34010: 'Dungeon_Elianodarea.lua',
    34030: 'Dungeon_Eltowerprotect.lua',
}
ELRIANODE_INVITATIONS = frozenset((710131, 168181, 710132, 710133, 168214, 168184,
                                  710134, 168213, 168183, 297707, 168261))
MAPS = aurora.MAPS + GIANTS + tuple(ELRIANODE)
_SOURCES = ('Dungeon_2019_Drabaki.lua', 'Dungeon_Devildom2_Portal.lua',
            'Dungeon_Devildom_Side3.lua', 'Dungeon_Devildom5_IronWall.lua')


@functools.lru_cache(maxsize=1)
def giant_definitions():
    data = client_data()
    if data.manifest['catalog_sha256'] != 'a633289850ef5b814aa338542e5f80e641153e99734c4f5c8c82f62bde49c3ba':
        raise ValueError('Daily ticket catalog changed')
    result = {}
    for identity, source in zip(GIANTS, _SOURCES):
        row = data.dungeon(identity)
        allowed = tuple(v for v in row['requireItemID'].values() if v)
        if (row['dataFileName'] != source or row.get('m_eDungeonType') != 6
                or (row.get('m_MinPlayerCount'), row.get('m_MaxPlayerCount')) != (1, 6)
                or row.get('m_iLimitPlayCount') != 5 or row.get('requireItemCount') != 1
                or 20 not in row['DUNGEON_CHECK_CONDITION'].values() or not allowed
                or any(data.item(t)['item_type'] != 7 or data.item(t)['metadata'] != 2 for t in allowed)):
            raise ValueError('Giant original admission definition changed')
        result[identity] = allowed
    return result


@functools.lru_cache(maxsize=2)
def elrianode_tickets(identity):
    data = client_data()
    row = data.dungeon(identity)
    allowed = tuple(v for v in row['requireItemID'].values() if v)
    if (row['dataFileName'] != ELRIANODE[identity]
            or len(allowed) != len(ELRIANODE_INVITATIONS)
            or set(allowed) != ELRIANODE_INVITATIONS
            or row['requireItemCount'] != 1 or row['m_iLimitPlayCount'] != 1
            or 20 not in row['DUNGEON_CHECK_CONDITION'].values()
            or any(data.item(t)['item_type'] != 7 or data.item(t)['metadata'] != 2 for t in allowed)):
        raise ValueError('Elrianode original daily admission changed')
    return allowed


def tickets(identity):
    if type(identity) is not int:
        raise ValueError('Daily ticket dungeon')
    if identity in GIANTS:
        return giant_definitions()[identity]
    if identity in ELRIANODE:
        return elrianode_tickets(identity)
    return aurora.tickets(identity)


def free_limit(identity):
    tickets(identity)
    return 5 if identity in GIANTS else 1


def enabled(identity):
    tickets(identity)
    return identity in GIANTS or identity in ELRIANODE or aurora.enabled()
