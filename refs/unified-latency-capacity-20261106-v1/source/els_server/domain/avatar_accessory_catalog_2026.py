"""Pinned original KIM set definitions for the isolated activity candidate."""
import functools
from types import MappingProxyType
import hashlib
import json
from els_server.domain.avatar_accessory_effects_2026 import SetEffects


SOURCE_SHA256 = '5270a80871596e1f1154a04021f31b53ba8c185713c39c27983a9c6a0f7fa188'


def load_original(raw):
    if type(raw) is not bytes:
        raise ValueError('Pinned original set definition bytes required')
    # Startup already calls this exact reader before opening listeners.
    # Values are frozen SetEffects with tuple fields; only the caller's
    # dictionary is independent, preserving its existing public contract.
    return dict(_definitions(raw))


@functools.lru_cache(maxsize=1)
def _definitions(raw):
    # Cache keys compare immutable byte contents, so changed source bytes
    # must pass the same original SHA check before any parsed value exists.
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned original set definition bytes required')
    document = json.loads(raw)
    definitions = {
        row['set_id']: SetEffects(
            row['avatar_accessory'],
            tuple(tuple(v) for v in row['tiers']),
            tuple(tuple(v) for v in row['variants']))
        for row in document['rows']
    }
    if len(definitions) != 11422 or sum(d.avatar_accessory for d in definitions.values()) != 2071:
        raise ValueError('Original set coverage changed')
    return MappingProxyType(definitions)
