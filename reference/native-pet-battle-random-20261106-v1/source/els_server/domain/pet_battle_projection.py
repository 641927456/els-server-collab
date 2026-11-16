"""Project already-authorized combat facts through the original A6B codec.

The flow supplies current FullUser encoding and frozen admitted entrants.
No actor admission, state transition, storage write or award happens here.
"""
import struct
from els_server.domain.pet_battle import Kind
from els_server.protocol import pet_battle_turn_messages as wire


def notice(match,entrants,user,*,result=None,previous=None):
    """user(owner, pet_vector) inserts shared encoded pets into FullUser."""
    sources={owner:{entry.fact.uid:entry for entry in pets}for owner,pets in entrants.items()}
    sides={side.uid:side for side in match.sides}
    def pet_state(owner,state):
        pet=sides[owner].pets[state.uid]
        return sources[owner][state.uid].record+struct.pack('>iii',pet.ability,state.hp,state.enchant)
    members=[]
    for state in match.snapshot():
        side=sides[state.uid]
        planned=()if side.actions is None else tuple((a.kind,a.target)for a in side.actions)
        pet_vector=struct.pack('>I',len(state.pets))+b''.join(pet_state(state.uid,p)for p in state.pets)
        members.append(wire.member(state.uid,user(state.uid,pet_vector),
            pet_vector,planned,state.active,state.defence_left))
    results=[]
    if result is not None:
        if previous is None:raise ValueError('Pet battle original pre-round snapshot required')
        before={s.uid:s for s in previous}
        for step in result.steps:
            acting=before[step.owner].active
            other=next(s for uid,s in before.items()if uid!=step.owner)
            after={s.uid:s for s in step.states}
            state=next(p for p in after[step.owner].pets if p.uid==acting)
            target=(step.target if step.kind==Kind.CHANGE else
                other.active if step.kind==Kind.ATTACK else 0)
            hp={p.uid:p.hp for side in step.states for p in side.pets}
            enchant={p.uid:p.enchant for side in step.states for p in side.pets}
            # Native32A6CB0 style0 plays Critical_Hit;3 is the original neutral
            # constructor style. Outcome1 shows evasion;2 displays amount.
            results.append(wire.action_result(pet_state(step.owner,state),step.kind,
                0 if step.critical else 3,1 if step.evaded else 2,
                step.healing if step.kind==Kind.HEAL else step.damage,target,hp,enchant,other.active))
            before=after
    return wire.turn(match.number if result is None else result.number,members,results)
