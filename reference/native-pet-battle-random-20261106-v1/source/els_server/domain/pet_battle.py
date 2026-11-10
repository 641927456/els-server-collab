"""Server-owned pet turns using approved combat values and current guide rules.

The flow must admit two actors and their three owned pets before constructing a
Match. This module neither grants rewards nor establishes ownership/eligibility.
CN guide: https://els.ztgame.com/game/004-1654-00356-497721.shtml?ms=672&mt=854
KR guide72 distinguishes defence3 per game from healing1 per round.
"""
from dataclasses import dataclass
from enum import IntEnum
from random import SystemRandom


class Kind(IntEnum):
    ATTACK=1
    DEFEND=2
    ENCHANT=3
    HEAL=4
    CHANGE=5


@dataclass(frozen=True)
class PetInput:
    uid:int
    attribute:int
    ability:int
    growth:tuple[int,int,int,int]


@dataclass(frozen=True)
class Action:
    kind:Kind
    target:int=0


@dataclass
class Pet:
    uid:int
    attribute:int
    ability:int
    points:int
    hp:int=100
    enchant:int=0


@dataclass
class Side:
    uid:int
    pets:dict[int,Pet]
    active:int
    defence_left:int=3
    heal_left:int=1
    submitted_active:int|None=None
    actions:tuple[Action,...]|None=None


@dataclass(frozen=True)
class PetState:
    uid:int
    ability:int
    hp:int
    enchant:int


@dataclass(frozen=True)
class SideState:
    uid:int
    active:int
    defence_left:int
    heal_left:int
    pets:tuple[PetState,...]


@dataclass(frozen=True)
class Step:
    slot:int
    first:bool
    owner:int
    kind:Kind
    target:int
    damage:int
    healing:int
    cheering:bool
    critical:bool
    evaded:bool
    patience:bool
    states:tuple[SideState,SideState]


@dataclass(frozen=True)
class Round:
    number:int
    steps:tuple[Step,...]
    states:tuple[SideState,SideState]
    winner:int|None


def _uid(value):
    if type(value)is not int or not 1<=value<2**63:raise ValueError('Pet battle UID')
    return value


class Match:
    def __init__(self,members,*,rng=None):
        """members contains two (actor UID, three PetInput facts) pairs."""
        if len(members)!=2:raise ValueError('Pet battle requires two actors')
        self.rng=SystemRandom()if rng is None else rng
        sides=[];actors=set();pet_ids=set()
        for owner,inputs in members:
            owner=_uid(owner)
            if owner in actors or len(inputs)!=3:raise ValueError('Pet battle distinct actors/three pets')
            actors.add(owner);pets={}
            for fact in inputs:
                uid=_uid(fact.uid)
                if uid in pet_ids or type(fact.attribute)is not int or fact.attribute not in(1,2,3):raise ValueError('Pet battle distinct native pets/attribute')
                if type(fact.ability)is not int or fact.ability not in(-1,0,1,2,3):raise ValueError('Pet battle growth choice')
                if len(fact.growth)!=4 or any(type(v)is not int or not 0<=v<=1000 for v in fact.growth):raise ValueError('Pet battle growth points')
                pet_ids.add(uid)
                ability=self.rng.randrange(4)if fact.ability==-1 else fact.ability
                pets[uid]=Pet(uid,fact.attribute,ability,fact.growth[ability])
            sides.append(Side(owner,pets,next(iter(pets))))
        self.sides=tuple(sides);self._owners={s.uid:s for s in sides}
        self.number=1;self.phase='selecting';self.winner=None

    def _side(self,owner):
        try:return self._owners[owner]
        except KeyError:raise ValueError('Pet battle actor absent')from None

    def snapshot(self):
        return tuple(SideState(s.uid,s.active,s.defence_left,s.heal_left,
            tuple(PetState(p.uid,p.ability,p.hp,p.enchant)for p in s.pets.values()))for s in self.sides)

    def _plan(self,side,actions,active,*,fill):
        if len(actions)!=3:raise ValueError('Pet battle three action slots')
        current=side.pets[side.active]
        if active is None and fill:
            active=side.active if current.hp>0 else self.rng.choice([p.uid for p in side.pets.values()if p.hp>0])
        if active not in side.pets or side.pets[active].hp<=0:raise ValueError('Pet battle living active pet')
        if current.hp>0 and active!=side.active:raise ValueError('Pet battle replacement requires change action')
        selected=active;defence=side.defence_left;healing=side.heal_left;result=[]
        for action in actions:
            alternatives=[p.uid for p in side.pets.values()if p.hp>0 and p.uid!=selected]
            legal=[Kind.ATTACK,Kind.ENCHANT]
            if defence:legal.append(Kind.DEFEND)
            if healing:legal.append(Kind.HEAL)
            if alternatives:legal.append(Kind.CHANGE)
            if action is None:
                if not fill:raise ValueError('Pet battle action slot is empty')
                # Choose a type first, then a replacement target: extra bench
                # pets must not increase the probability of choosing CHANGE.
                kind=self.rng.choice(legal)
                action=Action(kind,self.rng.choice(alternatives)if kind==Kind.CHANGE else 0)
            if type(action.kind)not in(int,Kind)or action.kind not in legal:raise ValueError('Pet battle action unavailable')
            kind=Kind(action.kind)
            if kind==Kind.CHANGE:
                if action.target not in alternatives:raise ValueError('Pet battle replacement target')
                selected=action.target
            elif action.target!=0:raise ValueError('Pet battle non-change logical target')
            if kind==Kind.DEFEND:defence-=1
            if kind==Kind.HEAL:healing-=1
            result.append(Action(kind,action.target))
        return active,tuple(result)

    def submit(self,owner,actions,active):
        side=self._side(owner);actions=tuple(actions)
        if side.actions is not None:
            if side.actions==actions and side.submitted_active==active:return False
            raise ValueError('Pet battle completed selection cannot change')
        if self.phase!='selecting':raise ValueError('Pet battle outside selection')
        active,actions=self._plan(side,actions,active,fill=False)
        side.active,side.submitted_active,side.actions=active,active,actions
        return True

    def timeout(self):
        if self.phase!='selecting':raise ValueError('Pet battle timeout outside selection')
        for side in self.sides:
            if side.actions is None:
                side.active,side.actions=self._plan(side,(None,None,None),None,fill=True)
                side.submitted_active=side.active
        return self.resolve()

    def _proc(self,pet,ability):
        return pet.ability==ability and pet.points>0 and self.rng.randrange(5000)<pet.points

    def _order(self,actions):
        first,second=self.sides;cheer={first.uid:False,second.uid:False}
        a,b=actions
        if (a.kind==Kind.CHANGE)!=(b.kind==Kind.CHANGE):return ((second,first)if a.kind==Kind.CHANGE else(first,second)),cheer
        if (a.kind==Kind.DEFEND)!=(b.kind==Kind.DEFEND):return ((first,second)if a.kind==Kind.DEFEND else(second,first)),cheer
        for side in self.sides:cheer[side.uid]=self._proc(side.pets[side.active],0)
        if cheer[first.uid]!=cheer[second.uid]:return ((first,second)if cheer[first.uid]else(second,first)),cheer
        return ((first,second)if self.rng.randrange(2)==0 else(second,first)),cheer

    def _act(self,side,other,action,defending,slot,first,cheering):
        pet=side.pets[side.active];victim=other.pets[other.active]
        damage=healing=0;critical=evaded=patience=False;target=pet.uid
        if action.kind==Kind.DEFEND:
            side.defence_left-=1;defending.add(side.uid)
        elif action.kind==Kind.ENCHANT:
            pet.enchant=2
        elif action.kind==Kind.HEAL:
            side.heal_left-=1;patience=self._proc(pet,1)
            healing=min(100-pet.hp,45 if patience else 30);pet.hp+=healing
        elif action.kind==Kind.CHANGE:
            pet.enchant=0;side.active=action.target;target=action.target
        else:
            target=victim.uid;boosted=pet.enchant>0;pet.enchant=0
            evaded=self._proc(victim,3)
            if not evaded:
                critical=self._proc(pet,2)
                advantage={(1,2),(2,3),(3,1)}
                base=30 if(pet.attribute,victim.attribute)in advantage else 10 if(victim.attribute,pet.attribute)in advantage else 20
                numerator=base;denominator=1
                if boosted:numerator*=3;denominator*=2
                if critical:numerator*=3;denominator*=2
                if other.uid in defending:denominator*=2
                # Native HP is i32: apply the approved multipliers together,
                # then truncate the positive result once.
                damage=numerator//denominator;victim.hp=max(0,victim.hp-damage)
                if victim.hp==0:victim.enchant=0
        if action.kind in(Kind.DEFEND,Kind.HEAL)and pet.enchant>0:pet.enchant-=1
        return Step(slot,first,side.uid,action.kind,target,damage,healing,cheering,
                    critical,evaded,patience,self.snapshot())

    def resolve(self):
        if self.phase!='selecting' or any(s.actions is None for s in self.sides):raise ValueError('Pet battle two completed selections required')
        steps=[];fainted=False
        for slot in range(3):
            order,cheering=self._order(tuple(s.actions[slot]for s in self.sides))
            defending=set()
            for i,side in enumerate(order):
                other=self.sides[1]if side is self.sides[0]else self.sides[0]
                steps.append(self._act(side,other,side.actions[slot],defending,slot,i==0,cheering[side.uid]))
                for victim in self.sides:
                    if victim.pets[victim.active].hp==0:
                        if all(p.hp==0 for p in victim.pets.values()):self.winner=other.uid if victim is side else side.uid
                        fainted=True
                if fainted:break
            if fainted:break
        self.phase='animating'
        return Round(self.number,tuple(steps),self.snapshot(),self.winner)

    def finish_animation(self):
        if self.phase!='animating':return False
        if self.winner is not None:self.phase='finished'
        else:
            self.number+=1;self.phase='selecting'
            for side in self.sides:side.actions=None;side.submitted_active=None;side.heal_left=1
        return True
