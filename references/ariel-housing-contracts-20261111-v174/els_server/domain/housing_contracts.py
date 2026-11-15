"""Original Ariel housing contract records and finite renewal terms."""
import hashlib
import struct

from els_server.game_data import client_data


RENEWAL_SECONDS = {136035: 2592000, 136088: 10368000}
RENEWALS = frozenset(RENEWAL_SECONDS)
VILLAGES = range(20000, 20014)
_RECORDS = {
    136035: ('6f5c4703eba27c4126e02a3270e2d2ae9f08b5431e7ade4cc09d0225642c93b7', 50000000),
    136088: ('e65117b44a9d403de82209443c9cca73b8c943163076b2a8dcf5e9c72aa7901e', 100000000),
}


def inventory_definitions():
    for template, (digest, ed) in _RECORDS.items():
        item = client_data().item(template)
        record = item['record']
        if (hashlib.sha256(record).hexdigest() != digest
                or (item['item_type'], item['metadata'], item['flags4'], item['flags8']) != (7, 0, 541069322, 56)
                or struct.unpack_from('<I', record, 0x10) != (0,)
                or struct.unpack_from('<ii', record, 0x1c) != (ed, 0)):
            raise ValueError('Original Ariel housing contract item source')
        yield template, (0, 4, 1)
