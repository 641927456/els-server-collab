"""User-authorized local contribution rules; not a recovered retail formula.

Only the existing authoritative clear writer can consume an Assessment. A9E
report alone never clears a run or pays a reward. The bonus rate is fixed.
"""
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import hashlib,json,struct


@lru_cache(maxsize=1)
def policy():
    raw=(Path(__file__).resolve().parents[1]/'data/dungeon_result_rules.json').read_bytes()
    value=json.loads(raw)
    if value['provenance']!='local_design':raise ValueError('Explicit local result rule provenance required')
    return value,hashlib.sha256(raw).hexdigest()


def admission_power(session):
    """Freeze a server equipment reference, not client-reported complete CP."""
    from els_server.domain.character_stats import combat_values
    character=session.account.character()
    items=session.account.get_inventory_snapshot()['items']
    values=combat_values(character,items)
    return session.account.uid,max(1.0,values[1],values[2])


@dataclass(frozen=True)
class Assessment:
    uid:int
    run_id:str
    dungeon:int
    version:str
    policy_sha256:str
    epoch:str
    score_bp:int
    rank:int
    completion:int
    power:float
    inputs:tuple
    reported:bool
    mvp:bool
    awards:tuple
    bonus_bp:int

    def identity(self):
        return dict(uid=self.uid,run_id=self.run_id,dungeon=self.dungeon,
            version=self.version,policy_sha256=self.policy_sha256,provenance='local_design',
            epoch=self.epoch,score_bp=self.score_bp,rank=self.rank,completion=self.completion,
            power=self.power,power_basis=policy()[0]['power_basis'],inputs=list(self.inputs),
            reported=self.reported,mvp=self.mvp,awards=list(self.awards),bonus_bp=self.bonus_bp)


def _winner(values,epoch,category,minimum):
    maximum=max(values.values())
    if maximum<minimum:return None
    tied=(uid for uid,value in values.items()if value==maximum)
    return min(tied,key=lambda uid:hashlib.sha256(f'{epoch}|{category}|{uid}'.encode('ascii')).digest())


def assess(members,epoch):
    from els_server.domain.dungeon_result_stats import current_statistics,cooldown_payloads
    rule,digest=policy();rows=[]
    cooldown=cooldown_payloads(members,frozenset(m.account.uid for m in members))
    for member in members:
        uid=member.account.uid;entry_uid,power=member.dungeon_result_power
        if entry_uid!=uid:raise ValueError('Dungeon result admitted power owner changed')
        stats=current_statistics(member)
        if stats is None:
            metrics=(0.0,)*5;award_values=(0.0,)*3
        else:
            damage=[values.get(uid,0.0)for values in stats['damage']]
            hp,mp,own_hp,own_mp=stats['recovery']
            metrics=(damage[3]+damage[6],damage[7],max(0.0,hp-own_hp),max(0.0,mp-own_mp),
                     struct.unpack('>f',cooldown[uid])[0])
            award_values=(damage[0]+damage[6],damage[7],hp+mp)
        rows.append((member,power,stats is not None,metrics,award_values))
    weights=tuple(rule['weights'][key]for key in('offense','reduction','party_hp','party_mp','cooldown'))
    totals=tuple(sum(Fraction(row[3][n])for row in rows)for n in range(5))
    active=sum(weight for weight,total in zip(weights,totals)if total)
    shares={m.account.uid:(sum(Fraction(weight)*Fraction(metrics[n])/total
                for n,(weight,total)in enumerate(zip(weights,totals))if total)/active if active else Fraction(0))
            for m,_,_,metrics,_ in rows}
    scores={uid:int(share*10000)for uid,share in shares.items()}
    mvp=members[0].account.uid if len(members)==1 else _winner(scores,epoch,'mvp',100)
    awards=tuple(_winner({m.account.uid:values[n]for m,_,_,_,values in rows},epoch,name,1)
                 for n,name in enumerate(('destroyer','guardian','healer')))
    total_power=sum(Fraction(power)for _,power,_,_,_ in rows)
    plans={}
    for member,power,reported,metrics,_ in rows:
        uid=member.account.uid;score=scores[uid]
        # Grade the exact share: three equal members must all reach100%,
        # despite their displayed shares being rounded down to33.33 each.
        completion=int(shares[uid]*total_power*100/Fraction(power))
        rank=next(rank for minimum,rank in rule['rank_thresholds']if completion>=minimum)if reported else 0
        flags=tuple(uid==winner for winner in awards)
        plans[uid]=Assessment(uid,member.reward_run_id,member.dungeon_id,rule['version'],digest,epoch,
            score,rank,completion,power,metrics,reported,uid==mvp,flags,
            rule['award_bonus_bp']if uid==mvp or any(flags)else 0)
    return plans


def prepare_clear(session):
    from els_server.domain.dungeon_result_stats import generation
    # Original group writers use a shallow private shadow. Resolve the exact
    # original actor already supplied by that writer, not a new room lookup
    # on the shadow's object identity.
    supply=getattr(session,'_raid_supply',None)or getattr(session,'_pve_clear_supply',None)
    original=supply['original_session']if supply is not None else session
    app=getattr(original,'application',None)
    room=app.world.dungeons.room(original)if app is not None else None
    members=tuple(room.members)if room is not None else(original,)
    if frozenset(m.account.uid for m in members)!=original.dungeon_participants:
        raise ValueError('Dungeon result admitted roster changed')
    owner=room if room is not None else original
    epoch=room.seed if room is not None else original.reward_run_id
    revision=(epoch,tuple((m.account.uid,generation(m),getattr(m,'dungeon_result_report',(None,0))[1])for m in members))
    saved=getattr(owner,'dungeon_result_assessment',None)
    if saved is None or saved[0]!=revision:
        saved=(revision,assess(members,epoch));owner.dungeon_result_assessment=saved
    return saved[1][original.account.uid]


def result_payload(payload,assessment):
    if(len(payload)!=516 or struct.unpack_from('>I',payload,27)[0]!=1
       or struct.unpack_from('>Q',payload,31)[0]!=assessment.uid or payload[0x10]!=1):
        raise ValueError('Owned successful original C1 source required')
    raw=bytearray(payload)
    # DA5DA0: wire379/387..391 -> member DTO174/17C..180.
    struct.pack_into('>f',raw,379,assessment.score_bp/100)
    raw[387]=assessment.rank;raw[388]=int(assessment.mvp)
    raw[389:392]=bytes(assessment.awards)
    return bytes(raw)
