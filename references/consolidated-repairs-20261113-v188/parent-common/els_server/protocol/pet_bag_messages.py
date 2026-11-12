"""Original B39/B3A selection and 104/105 pet inventory moves."""
import struct

from els_server.domain.fashion_state import empty_record, record
from els_server.protocol.companion_messages import event, pet_record

GROUP = 13
SLOTS = 16


def selected(pet=None, slots=(), *, result=0):
    # 227A740: result, D9C550 pet DTO, DD46E0 inventory vector.
    return event(0xb3a, struct.pack('>i', result) + pet_record(pet) +
                 struct.pack('>I', len(slots)) +
                 b''.join(record(item, position=(GROUP, slot)) for slot, item in slots))


def moved(changes=(), *, result=0):
    # Same vector and result order as the ordinary 234B280/105 reader.
    rows = b''.join(empty_record(*position) if item is None else record(item, position=position)
                    for position, item in changes)
    return event(0x105, struct.pack('>I', len(changes)) + rows + struct.pack('>i', result))


def auto_feed_setting(pet_uid=0, enabled=False, *, result=0):
    # 2280650 reads result, checkbox value and the selected pet's UID.
    return event(0x2f9, struct.pack('>iBQ', result, enabled, pet_uid))


def auto_fed(pet, template, slot, remaining):
    # 2DC6560 reads template, personality, nutrition, inventory vector,
    # active pet UID and absolute satiety.
    personality = sorted((int(key), points) for key, points in pet['personality'].items())
    allocation = b''.join(struct.pack('>ih', key, points) for key, points in personality)
    row = (empty_record(GROUP, slot) if remaining is None else
           record(remaining, position=(GROUP, slot)))
    return event(0x2fa, struct.pack('>iI', template, len(personality)) + allocation +
                 struct.pack('>hI', pet['nutrition'], 1) + row +
                 struct.pack('>Qh', pet['uid'], pet['satiety']))
