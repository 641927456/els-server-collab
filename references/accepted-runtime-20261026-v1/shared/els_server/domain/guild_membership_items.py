"""Two current source records needed by guild creation and quest35630.

Reader registration alone is not purchase, membership or quest admission.
Both use the existing native type7 special-inventory record; no expiry,
activation, grant or old-instance migration is introduced here.
"""
import hashlib
import struct
from els_server.game_data import client_data


def definitions():
    rows = (
        (110845, 0, 541069322, 0,
         'd270590f3bfc0461dbbb09f6fe7a7b00a4eefff11e6962b44621ca3809985a6b'),
        (400152, 2, 573575170, 500,
         'd19bb054b095cea9e29a8c8e4bc0c441dbfdc18938d2247e27bbafe84e52d07b'),
    )
    result = []
    for template, metadata, flags, stack, digest in rows:
        source = client_data().item(template)
        record = source['record']
        if (hashlib.sha256(record).hexdigest() != digest or
            (source['item_type'], source['metadata'], source['flags4'],
             source['flags8'], struct.unpack_from('<I', record, 0x10)[0]) !=
                (7, metadata, flags, 56, stack)):
            raise ValueError('Current guild item reader source')
        result.append(dict(template=template, metadata=metadata,
                           group=4, max_stack=stack or 1))
    return tuple(result)
