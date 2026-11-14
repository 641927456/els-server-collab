"""Pinned original, permanent ticket requirements for two ordinary dungeons."""
import functools
import hashlib
from els_server.game_data import client_data

# The item records and dungeon definitions are from the current CN client catalog.
# The official CN dungeon pages independently specify one ticket per entry.
SOURCES = {
    35100: ('Dungeon_Devildom5_Arena.lua', (118341, 118342, 118343, 118344),
            ('0f5f25c626074c45207152c1f1afc9b2fdd627b05382a5dc54a2c83adf965a33',
             '65a91c3d47fb3c30dd4cfe4fb129891dfc9c0b04b9c0aeef5a4db63302267d16',
             '9bb5fea54084085085811cb573543f4f891eb67defe40997064d08357dc4d2f4',
             '08f69b16aa14c74dcfd8b6d988923e5d72b7a74322898f6a151df8a05399b447')),
    35360: ('Dungeon_Devildom6_Garden.lua', (118651, 118652, 118653, 118654),
            ('e606353fda59310f3f93ed7253874e4cc70690df13a8197779cd3b2698e53188',
             'ea1a7fb99d7c208ece5dbe522bc1622899679996b5619bc4985b04d157eca84b',
             'c4fcc7fa5a25c1869d53fbb5a9b41e1fd4085c88687d75609bb5b2a9d927ee28',
             'acf4b6d6553789c92c01134f13243be287d66e5cbb0276306c24f5e88835a423')),
}

# Compatible recovery flips this one value to False; readers and receipts stay.
ADMISSION_ENABLED = True


def enabled():
    return ADMISSION_ENABLED


@functools.lru_cache(maxsize=1)
def definitions():
    client = client_data()
    if client.manifest['catalog_sha256'] != 'a633289850ef5b814aa338542e5f80e641153e99734c4f5c8c82f62bde49c3ba':
        raise ValueError('Permanent ticket catalog changed')
    result = {}
    for dungeon_id, (source, tickets, hashes) in SOURCES.items():
        dungeon = client.dungeon(dungeon_id)
        loaded = tuple(value for value in dungeon['requireItemID'].values() if value)
        conditions = tuple(dungeon['DUNGEON_CHECK_CONDITION'].values())
        if (dungeon['dataFileName'] != source or loaded != tickets
                or dungeon['requireItemCount'] != 1 or dungeon['m_iLimitPlayCount'] != 0
                or 20 in conditions or dungeon['m_MinLevel'] != 99
                or dungeon['m_MaxLevel'] != 99):
            raise ValueError('Permanent ticket dungeon source changed')
        for ticket_id, expected_hash in zip(tickets, hashes):
            native = client.item(ticket_id)
            if (native['item_type'] != 7 or native['metadata'] != 2
                    or hashlib.sha256(native['record']).hexdigest() != expected_hash):
                raise ValueError('Permanent ticket item source changed')
        result[dungeon_id] = tickets
    return result


def tickets(dungeon_id):
    if type(dungeon_id) is not int or dungeon_id not in definitions():
        raise ValueError('Unqualified permanent ticket dungeon')
    return definitions()[dungeon_id]
