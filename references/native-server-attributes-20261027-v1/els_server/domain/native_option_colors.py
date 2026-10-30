"""Immutable original option type and three independent set-color domains.

Each domain uses its own native field. Missing records stay absent, distinct
from a present record whose color is zero. Load once before player SQL work.
"""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT

SHA256='cd0808c9eae1e7e5458a3c5c67a7cdacef48af472b9c033466d8d2388bfbe400'
FIELDS=('TYPE','m_eElianodePieceEquipColorType','m_eArtifactSpiritSocketColorType',
        'm_eTenebrousSocketSetType','m_eCircuitItemColorType','m_eCircuitItemShapeType')
SOURCES=('60d333e1afde0519a0be8446f7034d8913f505cded1aca14fa59c71c12c20e33',
         '55f72d7ff222644a5309388a6d669d4a26f08013ec577ac394f7fd59f7246766')


def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SHA256:
        raise ValueError('Qualified original option color source required')
    value=json.loads(raw)
    if (value['schema']!=1 or tuple(value['fields'])!=FIELDS
            or tuple(v['sha256']for v in value['sources'])!=SOURCES
            or len(value['definitions'])!=70522 or len(value['profiles'])!=288):
        raise ValueError('Original option color coverage differs')
    profiles=tuple(tuple(row)for row in value['profiles'])
    return MappingProxyType({int(key):profiles[index]for key,index in value['definitions'].items()})


@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-option-color-sources.json').read_bytes())


def colors(option_ids,field,source):
    if type(option_ids)is not tuple or field not in(1,2,3,4):
        raise ValueError('Ordered original option IDs and color domain required')
    return tuple(source[v][field]if v in source else None for v in option_ids)
