"""Normal 4E2 active switching for loaded solo/local and shared dungeon actors."""
import math,uuid

def canonical(value,version):
    if type(value) is not str:raise ValueError('LuCiel run identity')
    parsed=uuid.UUID(value)
    if str(parsed)!=value or parsed.version!=version:raise ValueError('LuCiel run generation')

def actor(s):
    a=s.account;character=a.character()
    if (a.store is None or a.characters is None or character['uid']!=a.uid or character['unit_type']!=10
        or s.role!='game' or not s.item_test or s.client_build!='dx11_260923'):raise ValueError('LuCiel current actor')
    from els_server.game_data import client_data
    if client_data().unit(character['unit_class'])['unitType']!=10:raise ValueError('LuCiel current family')
    refs=[a,a.store,a.characters];values=[a.uid,a.account_id,s.shop_session_id,s.phase,character['unit_class']]
    app=getattr(s,'application',None)
    if app is not None:
        if (s.released or s.social_overflow or s.coop_error or s.identity['id']!=a.account_id
            or app.playing.get(s.identity['id']) is not s):raise ValueError('LuCiel live lease')
        refs.extend((app,app.world,app.playing,s.identity))
        values.append(s.identity['id'])
    return app,refs,values

def run_state(s,epoch=None):
    from els_server.domain.dungeon_routes import DungeonRun
    if (s.phase!='dungeon_active' or not s.enter_dungeon or not s.reward_test or not s.population_test
        or not s.dungeon_substage_synced or s.gate_stage_loading or s.dungeon_return_pending
        or s.clear_notified or getattr(s,'dungeon_failed',True) or s.part_end_notified or s.reward_receipt is not None
        or s.dungeon_end_payload is not None or getattr(s,'coop_error',None)):
        raise ValueError('LuCiel dungeon is not active')
    run=s.dungeon_run;refs=[]
    if run is not None:
        if (type(run) is not DungeonRun or run.identity!=s.dungeon_id or run.stage!=s.gate_stage
            or run.next is not None or run.ready_at is not None or run.portal_requested
            or type(run.part) is not int or run.part not in run.parts
            or type(run.started_at) not in (int,float) or not math.isfinite(run.started_at) or run.started_at<0):
            raise ValueError('LuCiel current admitted run')
        canonical(run.run_id,4)
        if epoch is not None and run.run_id!=epoch:raise ValueError('LuCiel shared run epoch')
        if epoch is None and run.run_id!=s.reward_run_id:raise ValueError('LuCiel solo reward generation')
        refs.extend((run,run.graph,run.current));run_values=(run.run_id,run.stage,run.part,run.visits,run.started_at)
    else:
        if s.dungeon_id!=30000 or type(s.gate_stage) is not int or not 0<=s.gate_stage<=2:raise ValueError('LuCiel base dungeon generation')
        run_values=(None,s.gate_stage)
    if epoch is None:canonical(s.reward_run_id,4)
    elif s.reward_run_id!=str(uuid.uuid5(uuid.UUID(epoch),'reward:'+str(s.account.uid))):raise ValueError('LuCiel shared owner reward generation')
    return refs,(s.dungeon_id,s.reward_run_id,s.gate_stage,getattr(s,'dungeon_participants',frozenset((s.account.uid,))),run_values)

def context(s):
    app,refs,values=actor(s)
    if s.phase=='town_ready':
        if app is not None:raise ValueError('Friends town uses actual membership context')
        if 0x227 not in s.completed or s.active_map!=s.account.get_location()['map']:raise ValueError('LuCiel local town not ready')
        values.extend((s.active_map,repr(s.account.get_location())))
        return dict(refs=tuple(refs),values=tuple(values),world=None,room=None,entry=None,targets=())
    if s.phase!='dungeon_active':raise ValueError('LuCiel unsupported active phase')
    world=app.world if app else None;room=world.dungeons.transport_room(s) if world else None;targets=()
    if room is None:
        if ((world and (s in world.party_of or s in world.members)) or getattr(s,'solo_challenge_party',None) is not None
            or getattr(s,'active_challenge',None) is not None or getattr(s,'challenge_deadline',None) is not None
            or getattr(s,'dungeon_participants',frozenset((s.account.uid,)))!=frozenset((s.account.uid,))):raise ValueError('LuCiel unsupported solo context')
        extra,run=run_state(s);refs.extend(extra);values.append(run)
    else:
        from els_server.domain.friends_dungeon import Room
        if (type(room) is not Room or world.dungeons.room(s) is not room or room.phase!='active'
            or room.identity!=s.dungeon_id or not 2<=len(room.members)<=6 or not app.config.friends_coop_enabled
            or room.party.get('run') is not room or room.party.get('challenge')
            or room.party.get('challenge_pending') or tuple(room.party['members'])!=room.members
            or s not in room.members or len({m.account.uid for m in room.members})!=len(room.members)):
            raise ValueError('LuCiel unsupported shared room')
        canonical(room.seed,4);participants=frozenset(m.account.uid for m in room.members)
        refs.extend((room,room.party,room.members));values.extend((room.identity,room.seed,room.phase,room.leader))
        from els_server.domain.friends_world import Mailbox
        for member in room.members:
            if (member.application is not app or member.released or member.social_overflow or member.coop_error
                or member.role!='game' or member.client_build!='dx11_260923' or member.identity['id']!=member.account.account_id
                or app.playing.get(member.identity['id']) is not member or world.dungeons.transport_room(member) is not room
                or world.dungeons.room(member) is not room or world.party_of.get(member) is not room.party
                or member.dungeon_participants!=participants or member.gate_stage!=s.gate_stage
                or type(member.mailbox) is not Mailbox):raise ValueError('LuCiel changed shared member')
            extra,run=run_state(member,room.seed);refs.extend((member,member.account,member.identity,member.mailbox,*extra))
            values.extend((member.account.uid,member.account.account_id,member.shop_session_id,run,
                member.mailbox.bytes,tuple(member.mailbox.messages),tuple(member.mailbox.moves.items())))
        targets=tuple(m for m in room.members if m is not s)
    # Shared Room has no cached town entry to replace; only validated peer mailboxes change.
    return dict(refs=tuple(refs),values=tuple(values),world=world,room=None,entry=None,targets=targets)
