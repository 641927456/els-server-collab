"""Explicit local Aurora free admission policy, pinned to original CN records."""
import functools
import hashlib
from els_server.game_data import client_data

MAPS = (34530, 34540)
TICKETS = (711786, 711787, 711788, 711789)
RECORD_SHA256 = (
    '54d71ba993c64305584fb223455a96da9c12ff7b6f8792fc2e2dd0b1b5703963',
    'd6a89584b3a134bc3013230aafa1846d5f40085faedc99b60adec1ae281720fa',
    '252513873a4147cab76241335dadfad1e675f9ea022983fdb9d9cbea3cd5dbbd',
    'f2af795b4692db5e107806021a275ea2a24a80e12e238caa03da2f6af115bc8d',
)

# Compatible code-only recovery sets this False, retaining both readers and
# receipts so committed runs can still be read and replayed.
ADMISSION_ENABLED = True


def enabled():
    return ADMISSION_ENABLED


@functools.lru_cache(maxsize=1)
def definitions():
    data = client_data()
    if data.manifest['catalog_sha256'] != 'a633289850ef5b814aa338542e5f80e641153e99734c4f5c8c82f62bde49c3ba':
        raise ValueError('Aurora catalog changed')
    expected_conditions = {34530: (16, 20, 63), 34540: (16, 37, 20, 63)}
    expected_source = {34530: 'Dungeon_Devildom3_Suburbs.lua', 34540: 'Dungeon_Devildom3_Train.lua'}
    for dungeon in MAPS:
        row = data.dungeon(dungeon)
        if (row['dataFileName'] != expected_source[dungeon]
                or tuple(row['DUNGEON_CHECK_CONDITION'].values()) != expected_conditions[dungeon]
                or tuple(v for v in row['requireItemID'].values() if v) != TICKETS
                or row['requireItemCount'] != 1 or row['m_iLimitPlayCount'] != 1
                or row['m_MinLevel'] != 99 or row['m_MaxLevel'] != 99):
            raise ValueError('Aurora original admission definition changed')
    for template, digest in zip(TICKETS, RECORD_SHA256):
        row = data.item(template)
        if (row['item_type'] != 7 or row['metadata'] != 2
                or hashlib.sha256(row['record']).hexdigest() != digest):
            raise ValueError('Aurora original ticket record changed')
    return {dungeon: TICKETS for dungeon in MAPS}


def tickets(dungeon):
    if type(dungeon) is not int or dungeon not in definitions():
        raise ValueError('Unqualified Aurora dungeon')
    return definitions()[dungeon]
