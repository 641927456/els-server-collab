"""Saved mentor pairs inside an actual party; shared producers own each writer."""
from pathlib import Path
from els_server.domain.character_rules import CLASSES
from els_server.domain.careers import PARENTS
from els_server.storage import mentor_relations as storage


def branch(unit_class):
    while CLASSES[unit_class]['stage']>1:
        unit_class=PARENTS[unit_class]
    return unit_class if CLASSES[unit_class]['stage']==1 else None


def percentages(teacher_class,student_class):
    same=CLASSES[teacher_class]['base_class']==CLASSES[student_class]['base_class']
    route=branch(student_class)
    return 50+(30 if same else 0)+(20 if same and route is not None and route==branch(teacher_class)else 0)


def effects(db,members,room,dungeon,*,waiting=False):
    """Run once inside the original source's guarded SQL transaction."""
    if room is None and not waiting:return {}
    members=tuple(members)
    if len(members)<2:return {}
    app=members[0].application;world=app.world
    party=world.party_of.get(members[0])
    if party is None:return {}
    if any(world.party_of.get(s)is not party for s in members):
        raise ValueError('Mentor party roster changed')
    if waiting:
        if tuple(party['members'])!=members:raise ValueError('Mentor waiting roster changed')
        if party.get('run')is not None or party.get('union_runs'):return {}
        from els_server.domain.equipment_engrave_flow import current_lease
        if any(s.phase!='town_ready' or not current_lease(s) or s not in world.members for s in members):return {}
    elif (room.owner_party is not party or room.party.get('run')is not room or tuple(room.members)!=members
            or any(world.dungeons.room(s)is not room for s in members)):
        raise ValueError('Mentor play is outside the actual shared room')
    actual=Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()
    rows={}
    for s in members:
        if s.application is not app or Path(s.account.store.path).resolve()!=actual:
            raise ValueError('Mentor party uses another application/save')
        storage.require_owner(db,s.account.uid,s.account.account_id)
        row=db.execute('SELECT unit_class,level FROM characters WHERE uid=?',(s.account.uid,)).fetchone()
        rows[s.account.uid]=dict(unit_class=row[0],level=row[1])
    from els_server.domain.seal_quests import appropriate_level_range
    from els_server.game_data import client_data
    low,high=appropriate_level_range(client_data().dungeon(dungeon))
    result={}
    for owner,row in rows.items():
        saved=storage.relation(db,owner)
        if saved is None or not saved['is_student'] or saved['partner']not in rows or row['level']>=99:continue
        teacher=rows[saved['partner']]
        if CLASSES[teacher['unit_class']]['stage']<2:continue
        fact=dict(teacher=saved['partner'],student=owner,generation=saved['generation'],
            teacher_class=teacher['unit_class'],student_class=row['unit_class'],student_level=row['level'],
            xp_percent=percentages(teacher['unit_class'],row['unit_class']),fatigue_free=low<=row['level']<=high)
        result[owner]=fact
        result[saved['partner']]=dict(fact,xp_percent=0)
    return result


def waiting_fatigue_free(db,s,dungeon):
    party=s.application.world.party_of.get(s)
    if party is None:return False
    return effects(db,tuple(party['members']),None,dungeon,waiting=True).get(s.account.uid,{}).get('fatigue_free',False)


def opponents(db,members):
    """The sealed two-owner round supplies these actual opposing actors."""
    for member in members:
        owner=member.account.uid;saved=storage.relation(db,owner)
        if saved is None or not saved['is_student']:continue
        if saved['partner']not in {m.account.uid for m in members}:continue
        student=storage.character(db,uid=owner)
        teacher=storage.character(db,uid=saved['partner'])
        if student['level']>=99 or CLASSES[teacher['unit_class']]['stage']<2:return None
        return dict(student=owner,teacher=saved['partner'],generation=saved['generation'],
            student_level=student['level'],student_class=student['unit_class'],
            teacher_class=teacher['unit_class'],xp_percent=0,fatigue_free=False)
    return None


def black_gate(s,db,key,event,proof):
    from els_server.storage.mentor45000_scope import black_gate_witness
    if not black_gate_witness(s.dungeon_run,key,event,proof):return []
    room=s.application.world.dungeons.room(s)
    if room is None:return []
    from els_server.domain.account_fishing_tasks import actor_binding,actor_guard
    checks=[actor_guard(m,actor_binding(m))for m in room.members]
    def guard(writer):
        for check in checks:check(writer)
        if s.application.world.dungeons.room(s)is not room or not black_gate_witness(s.dungeon_run,key,event,proof):
            raise ValueError('Mentor BlackGate source changed')
        return True
    guard(db)
    effect=effects(db,tuple(room.members),room,38300).get(s.account.uid)
    if effect is None:return []
    from els_server.storage.mentor_quests import record
    return record(db,s.account.uid,key+':mentor-black-gate',effect,
        dict(kind='black_gate',dungeon=38300,npc=1367),guard)
