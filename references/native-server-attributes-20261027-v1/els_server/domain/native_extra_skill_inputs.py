"""Independent extra-rank inputs from the actual shared character skill DTO.

The final CD7160 record vector is ordinary learned rows when Force ownership is
empty, and owned Force grades otherwise. It is not an empty auxiliary vector.
87A6E0/902B60 replaces this source even when the owned ordinary-copy branch is
skipped; ordinary55B does not replace it. Source production alone does not attest
a successful native copy/transport write.
"""
from dataclasses import dataclass
from els_server.domain import native_skill_delivery_sources as sources


@dataclass(frozen=True)
class CopiedRanks:
    ordinary:tuple
    unsealed:tuple
    extra:tuple


def _rows(rows):
    if (type(rows)is not tuple or len(rows)>4096
            or any(type(row)is not tuple or len(row)!=2
                or type(row[0])is not int or not 0<row[0]<2**31
                or type(row[1])is not int or not 1<=row[1]<=255 for row in rows)):
        raise ValueError('Bounded complete native extra-rank pairs required')
    #902BC0 keeps distinct grades and inserts lexicographically by(ID,rank).
    return tuple(sorted(set(rows)))


def from_character_field(raw):
    # Reuse the complete canonical shape gate; do not parse an arbitrary suffix.
    sources.copied_preset(raw)
    reader=sources._Reader(raw)
    sources._records(reader,slots=True)
    for _ in range(reader.count(2)):reader.take(12)
    ordinary=sources._records(reader)
    reader.take(4);unsealed=sources._ids(reader);reader.take(2)
    sources._preset(reader)
    extra=sources._records(reader,seal_history=True)
    reader.take(1);reader.finish()
    return CopiedRanks(tuple(sorted(ordinary)),unsealed,_rows(extra))


def after_copy(copied):
    if type(copied)is not CopiedRanks:
        raise ValueError('Complete actual copied extra-rank source required')
    # All paths87B2ED/87B2F9/87B304 join87B33E before902B60. Only the
    # earlier ordinary8F5F00/8F5840/8F5E90 calls are skipped for the owner.
    return _rows(copied.extra)


def after_increment(previous,rows):
    incoming=_rows(rows)
    # A positive incremental notice cannot establish the unknown old vector.
    if previous is None:return None
    return _rows(_rows(previous)+incoming)


def after_extraction(previous,pair):
    removal=_rows((pair,))[0]
    if previous is None:return None
    return tuple(row for row in _rows(previous)if row!=removal)
