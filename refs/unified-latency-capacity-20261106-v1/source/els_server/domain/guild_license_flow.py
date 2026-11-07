"""Current normal Ariel EA purchase, finite110845 entry only."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol.protocol_codec import Event
from els_server.protocol.npc_trade_messages import purchase_request, purchase_ack
from els_server.storage.npc_trade import purchase
from els_server.storage.reward_state import validate_balances

WRITER_ENABLED = True


def _selected(s):
    return bool(getattr(s,'application',None) is not None and current_lease(s)
                and s.role=='game' and 0x28 in s.completed
                and s.account.characters is not None and s.account.store is not None
                and s.account.store.uid==s.account.uid)


class _ActorBinding:
    # Retain strong references: identity comparisons cannot be defeated by
    # replacing a root together with app.accounts while current_lease stays true.
    def __init__(self,refs,values):self.refs,self.values=refs,values
    def __eq__(self,other):
        return (isinstance(other,_ActorBinding) and self.values==other.values
                and len(self.refs)==len(other.refs)
                and all(a is b for a,b in zip(self.refs,other.refs)))


def _actor(s):
    # Reply identity is independent of purchase/task/membership eligibility.
    if not _selected(s):raise ValueError('Guild reply actor is retired')
    a=s.account;app=s.application;root=a.root;world=app.world
    if not app.registry.enabled(a.account_id):raise ValueError('Guild account disabled')
    if root.root is not root or root.characters is not a.characters or root.account_id!=a.account_id:
        raise ValueError('Guild original root/character registry')
    room=world.dungeons.room(s)
    town_key=world.members.get(s);town_room=world.towns.get(town_key)
    refs=(s,a,a.store,a.characters,root,root.character_accounts,root.characters,
          getattr(root,'store',None),app,app.config,app.accounts,
          app.playing,s.identity,app.registry,world,world.dungeons,room,
          world.members,world.towns,town_room,
          None if town_room is None else town_room.get(s),s.dungeon_run)
    values=(a.account_id,a.uid,a.store.uid,a.characters.account_id,root.account_id,
            s.role,s.phase,s.client_build,s.item_test,s.shop_session_id,
            s.active_map,s.pending_map,s.enter_town,s.dungeon_return_pending,
            s.dungeon_id,getattr(s,'released',False),frozenset(s.completed),town_key,
            str(Path(a.store.path).resolve()),str(Path(a.characters.path).resolve()),
            str(Path(app.config.state_file).resolve()),str(Path(app.registry.path).resolve()),
            json.dumps(s.identity,sort_keys=True),json.dumps(a.get_location(),sort_keys=True))
    return _ActorBinding(refs,values)


def reply_capture(s):
    try:captured=_actor(s)
    except (ValueError,AttributeError,TypeError,sqlite3.Error):return None
    def guard():
        if _actor(s)!=captured:raise ValueError('Guild original reply actor changed')
    return guard


def guarded_reply(guard,encode):
    if guard is None:return []
    try:
        guard();events=encode();guard()
        from els_server.protocol.protocol_codec import encode_event
        for event in events:encode_event(event)
        guard();return events
    except (ValueError,AttributeError,TypeError,UnicodeError,OverflowError,sqlite3.Error):
        return []


def _facts(s):
    from els_server.storage.local_state import TOWN_SCENES
    if not _selected(s) or s.phase!='town_ready':
        raise ValueError('Guild license requires current selected town session')
    location=s.account.get_location()
    town=location['map']
    if town not in range(20000,20014) or town not in TOWN_SCENES or s.active_map!=town:
        raise ValueError('Guild license original town source')
    if (not s.enter_town or s.dungeon_return_pending or s.pending_map!=town
            or not {0x225,0x227}.issubset(s.completed)
            or s.application.world.dungeons.room(s) is not None
            or s.application.world.members.get(s)!=(1,town)
            or s not in s.application.world.towns.get((1,town),{})):
        raise ValueError('Guild requires completed stable original town arrival')
    return (_actor(s),TOWN_SCENES[town])


def _failed(s,guard):
    return guarded_reply(guard,lambda:_failure_events(s))


def _failure_events(s):
    if not _selected(s):
        raise ValueError('Guild license without current selected owner')
    path=Path(s.account.store.path).resolve().as_uri()+'?mode=ro'
    with closing(sqlite3.connect(path,uri=True,timeout=10)) as db:
        row=db.execute('SELECT b.ed,b.experience,b.revision FROM reward_balances b '
            'JOIN character_owners o ON o.uid=b.uid JOIN characters c ON c.uid=b.uid '
            'WHERE b.uid=? AND o.account_id=?',(s.account.uid,s.account.account_id)).fetchone()
    return [Event(0x201,kind=0xeb,payload=purchase_ack(validate_balances(row)['ed'],result=-1))]


def handle(s,event,sequence):
    if not (s.item_test and s.client_build=='dx11_260923'
            and event.event_id==0x202 and event.kind==0xea):
        return None
    try:
        entries,merchant=purchase_request(event.payload)
    except ValueError:
        return None  # Original EA parser owns malformed/nonfinite requests.
    if not any(template==110845 for template,count in entries):
        return None
    reply_guard=reply_capture(s)
    if reply_guard is None:return []
    if (not WRITER_ENABLED or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
            or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
        return _failed(s,reply_guard)
    try:
        expected=_facts(s)
        def guard():
            reply_guard()
            if _facts(s)!=expected:
                raise ValueError('Guild license live identity/source changed')
        operation=s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence)
        return purchase(s.account.store.path,s.account.uid,s.active_map,event.payload,operation,
                        guild_account_id=s.account.account_id,guild_guard=guard)
    except (ValueError,sqlite3.Error):
        return _failed(s,reply_guard)
