"""Native daily free entries and owned extra-entry tickets, without new pools."""
import functools
from els_server.game_data import client_data
from els_server.domain import aurora_ticket_rules as aurora

GIANTS = (34310, 34360, 34730, 35110)
MAPS = aurora.MAPS + GIANTS
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


def tickets(identity):
    if type(identity) is not int:
        raise ValueError('Daily ticket dungeon')
    if identity in GIANTS:
        return giant_definitions()[identity]
    return aurora.tickets(identity)


def free_limit(identity):
    tickets(identity)
    return 5 if identity in GIANTS else 1


def enabled(identity):
    tickets(identity)
    return identity in GIANTS or aurora.enabled()
