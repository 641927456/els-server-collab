"""Local active-offer-derived metadata, not an official full-catalog policy.

The caller binds a trusted ledger read callback at construction. It must read
one complete, atomic active-offer snapshot, not a bag or a client item catalog.
Only wire bytes for the original item record are accepted. This component has
no SQL, inventory producer, dispatch or mutable per-query cache.
"""
from dataclasses import dataclass
from els_server.protocol.tradeboard_metadata_item import read_item
from els_server.protocol.tradeboard_metadata_messages import request, acknowledgement, PAGE_SIZE

ACTIVE_OFFER_SOURCE = 'tradeboard-active-offer-ledger-v1'


class MetadataNotReady(ValueError):
    pass


@dataclass(frozen=True)
class ActiveOffer:
    offer_id: int
    native_item: bytes
    active: bool


@dataclass(frozen=True)
class ActiveOfferSnapshot:
    source: str
    revision: str
    ready: bool
    complete: bool
    offers: tuple


class MetadataQuery:
    def __init__(self, read_active_offers, item_type_for, valid_pet_id, valid_mount_id):
        if not all(callable(value) for value in (
                read_active_offers, item_type_for, valid_pet_id, valid_mount_id)):
            raise ValueError('Bound ledger and native catalog providers required')
        self._read = read_active_offers
        self._item_type = item_type_for
        self._pet = valid_pet_id
        self._mount = valid_mount_id

    def query(self, payload):
        selected = request(payload)
        snapshot = self._read()               # Exactly one actual ledger read
        if (type(snapshot) is not ActiveOfferSnapshot
                or type(snapshot.source) is not str or snapshot.source != ACTIVE_OFFER_SOURCE
                or type(snapshot.revision) is not str or not snapshot.revision
                or snapshot.ready is not True or snapshot.complete is not True
                or type(snapshot.offers) is not tuple):
            raise MetadataNotReady('Complete actual active-offer snapshot unavailable')
        if len(snapshot.offers) > 65536:
            raise ValueError('Active-offer snapshot bound')
        pools = {kind: set() for kind in (1, 2, 3, 4)}
        seen = set()
        for offer in snapshot.offers:
            if (type(offer) is not ActiveOffer or type(offer.offer_id) is not int
                    or not 0 < offer.offer_id < 2**63 or offer.active is not True
                    or offer.offer_id in seen):
                raise ValueError('Exact unique active offer record required')
            seen.add(offer.offer_id)
            item = read_item(offer.native_item)
            item_type = self._item_type(item.template)
            if type(item_type) is not int or not 0 <= item_type <= 31:
                raise ValueError('Original item type unavailable')
            pools[1].add(item.template)
            for group in item.option_groups:
                pools[2].update(group)
            if item_type == 12 and item.pet_data_id != 0:
                if item.pet_data_id < 0 or self._pet(item.pet_data_id) is not True:
                    raise ValueError('Unknown native pet data ID')
                pools[3].add(item.pet_data_id)
            if item_type == 13 and item.mount_data_id != 0:
                if item.mount_data_id < 0 or self._mount(item.mount_data_id) is not True:
                    raise ValueError('Unknown native mount data ID')
                pools[4].add(item.mount_data_id)
        page = sorted(value for value in pools[selected.kind] if value > selected.cursor)[:PAGE_SIZE]
        return acknowledgement(selected.kind, page)
