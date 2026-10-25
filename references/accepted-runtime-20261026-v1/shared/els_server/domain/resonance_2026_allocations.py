"""Positive allocation planning from the fixed client's15stat definitions.

This is a local business candidate, not a network handler. The caller supplies
authoritative current allocations, available points and temporary bonus points.
It neither derives points from level nor initializes/resets a character page.
"""
from dataclasses import dataclass
import hashlib
import json

DEFINITION_SHA256='44fafbf5bd676453af0c5ad9d38b83bb853ae9a9a4a0d123f77dfbb0b0cb992a'


@dataclass(frozen=True)
class ResonanceStat:
    stat_id: int
    symbol: str
    tab: int
    maximum: int


@dataclass(frozen=True)
class AllocationPlan:
    points: tuple
    remaining_points: int
    spent_points: int


@dataclass(frozen=True)
class ResonanceAllocations:
    stats: tuple

    @classmethod
    def from_original(cls, raw):
        if hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:
            raise ValueError('Unverified original resonance definition')
        data=json.loads(raw)
        return cls(tuple(ResonanceStat(r['stat_id'],r['symbol'],r['tab'],r['maximum']) for r in data['rows']))

    def stat(self, stat_id):
        if type(stat_id) is not int:
            raise ValueError('Integer resonance type required')
        for row in self.stats:
            if row.stat_id==stat_id:return row
        raise ValueError('Resonance type absent from current client definition')

    def _points(self, rows, *, bonus=False, additions=False):
        if type(rows) is not tuple:
            raise ValueError('Explicit immutable point pairs required')
        out={}
        for row in rows:
            if type(row) is not tuple or len(row)!=2:
                raise ValueError('Invalid point pair')
            key,value=row;definition=self.stat(key)
            if key in out or type(value) is not int or value<(1 if additions else 0) or value>2**31-1:
                raise ValueError('Invalid or duplicate point value')
            if not bonus and value>definition.maximum:
                raise ValueError('Per-stat allocation limit exceeded')
            out[key]=value
        return out

    def add(self, *, current, additions, available_points, bonus_points):
        """Validate all positive additions before returning a new immutable plan.

        Temporary bonus points consume the same displayed per-stat capacity
        (37907A0), but are not copied into the character's invested-point map.
        Refunds require the original item/period rules and are not accepted here.
        """
        if type(available_points) is not int or not 0<=available_points<=2**31-1:
            raise ValueError('Authoritative available point budget required')
        old=self._points(current);delta=self._points(additions,additions=True)
        bonus=self._points(bonus_points,bonus=True)
        spent=sum(delta.values())
        if spent>available_points:
            raise ValueError('Insufficient available resonance points')
        for key,value in delta.items():
            if old.get(key,0)+bonus.get(key,0)+value>self.stat(key).maximum:
                raise ValueError('Allocation plus temporary bonus exceeds stat limit')
        updated=dict(old)
        for key,value in delta.items():updated[key]=updated.get(key,0)+value
        return AllocationPlan(tuple(sorted(updated.items())),available_points-spent,spent)
