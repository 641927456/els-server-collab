"""Normal official1v1 admission, original battle reports and durable settlement."""
import sqlite3,struct
from els_server.domain import pvp_actor
from els_server.domain.pvp_registration import Registrations,_envelope
from els_server.domain.pvp_loading import Loading
from els_server.domain.pvp_round import Rounds
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import pvp_play_messages as play,pvp_result_messages as result_wire
from els_server.protocol import quest_messages,dungeon_messages,pvp_loading_messages
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.pvp_settlement import settle


class FriendsPVP:
    def __init__(self,world):
        self.world=world;self.registrations=Registrations(world)
        self.loading=Loading(world,self.registrations);self.rounds=Rounds(self.loading)
        self.support={}
        from els_server.domain.duel_flow import Duels
        self.duels=Duels(self)
        from els_server.domain.practice_pvp import Practice
        self.practice=Practice(self)

    def room(self,s):return self.loading.room(s)

    def support_status(self,app,account_id,relay,status):
        from els_server.domain.pvp_support import decode
        value=decode(status)
        self.support[account_id]=(relay,value['epoch'],value['source_sha256'],value['ready'])
        s=app.playing.get(account_id)
        if s is not None and not value['ready']:
            live=s in self.registrations.queue or s in self.registrations.offers or s in self.duels.pending or self.room(s)is not None or s in self.practice.visitors
            if live:
                # Release through the existing native-connection loss policy;
                # never invent maxHP or leave an unreportable timed match open.
                self.disconnect(s);s.coop_error='对战支持组件不可用，请更新并重启启动器。'

    def support_lost(self,account_id,relay):
        old=self.support.get(account_id)
        if old is not None and old[0]is relay:self.support.pop(account_id)

    def support_binding(self,s):return self.support.get(s.account.account_id)

    def support_ready(self,s):
        value=self.support_binding(s)
        return value is not None and value[3] is True

    def _settle(self,s):
        result=self.rounds.result(s)
        if result is None:return
        challenge=result.room.kind in('challenge','practice')
        prepared={}
        def encode(db,source,rows):
            from els_server.storage.seal_quests import load_character,current_slots,_state
            from els_server.storage.inventory_state import load_items
            from els_server.storage.normal_fatigue import snapshot as fatigue
            entries=[]
            for m,row in zip(source.members,rows):
                killed=source.reason=='kill';win=row['win']
                entries.append(result_wire.player(m.account.uid,1 if win or source.killer is None else 2,
                    int(killed and win),int(killed and win),int(killed and m is source.victim),
                    row['rating_delta']if challenge else row['after']['rating']-row['before']['rating'],
                    row['ap_delta']if challenge else row['after']['ap']-row['before']['ap'],row['awarded_exp'],win))
            events={}
            for m,row in zip(source.members,rows):
                role=load_character(db,m.account.uid,m.account.account_id);items=load_items(db,m.account.uid)
                spirit=fatigue(db,m.account.uid,m.account.account_id)['current']
                payload=result_wire.result(source.members.index(source.killer)if source.killer else 0,
                    source.elapsed,entries,spirit=spirit,draw=source.killer is None,abnormal=source.reason=='leave',channel=9 if source.room.kind=='practice'else 12)
                group=[Event(0x201,kind=0xc2,payload=payload)]
                if not challenge and row['quests']:group.append(quest_messages.progress(row['quests']))
                group.append(dungeon_messages.return_user_sync(m.account.get_location(),current_slots(db,role),
                    row['balances'],items,role,inventory_updates=[]))
                # D9 carries empty legacy quest vectors. Restore this actor's
                # committed task table after it, as the ordinary observer does.
                state=_state(db,m.account.uid,items,character=role)
                if any(state.get(key)for key in('active','completed','item_active','item_completed')):
                    group.append(quest_messages.initialization(state))
                events[m]=tuple(group)
            # Allocate/encode every mailbox before the actual economic commit.
            prepared['boxes']=_prepared_boxes([(m,events[m])for m in source.members],())
            return events
        if challenge:
            from els_server.storage.duel_results import settle as settle_challenge
            events,receipt,replayed=settle_challenge(self.rounds,s,encode=encode)
        else:events,receipt,replayed=settle(self.rounds,s,encode=encode)
        if replayed:
            prepared['boxes']=_prepared_boxes([(m,events[m])for m in result.members],())
        result.room.phase='result'
        for m in result.members:m.phase='pvp_result'
        for m,box in prepared['boxes'].items():m.mailbox=box

    def _remove(self,s):
        room=self.room(s)
        if room is None:return
        self.loading.rooms.pop(s,None)
        if not any(self.room(m)is room for m in room.members):self.rounds.rounds.pop(room.seed,None)

    def _finish(self,s,payload,*,ack=True):
        room=self.room(s)
        if room is None:raise ValueError('PvP original result room absent')
        if room.kind=='practice':return self.practice.finish(s,payload,ack=ack)
        if room.phase in ('active','reporting'):
            self.rounds.leave(s);self._settle(s)
        elif room.phase=='loading':
            for other in room.members:
                if other is not s and not other.released:other.coop_error='Official match ended before both players loaded'
        elif room.phase!='result':raise ValueError('PvP departure phase')
        response=([dungeon_messages.end_ack()]if ack else[])+[s.saved_user_sync()]
        for e in response:encode_event(e)
        # An active67 may seal its result in this call. Deliver that original
        # C2/F3 before acknowledging departure and restoring the town Unit.
        response=s.mailbox.drain()+response
        self.duels.finished(s,room)
        self._remove(s);s.phase='map_loading';s.pending_map=None;s.dungeon_return_pending=True
        s.pvp_end_payload=bytes(payload);s.inventory_town_sync_sent=True
        return response

    def request(self,s,event,sequence):
        if event.event_id!=0x202:return None
        kind=event.kind;room=self.room(s)
        response=self.practice.request(s,event,sequence)
        if response is not None:return response
        response=self.duels.request(s,event,sequence)
        if response is not None:return response
        if kind==0x828:return self.duels.position(s,event)
        if kind in(0x7d4,0x342,0x34a)and s in self.duels.pending:
            # The original shared actor may own either queue consent or a
            # challenge invitation, never both concurrently.
            if kind==0x7d4 and event.payload[:4]==struct.pack('>i',5):
                return [Event(0x201,kind=0x7d5,payload=struct.pack('>ii',-1,5))]
            if kind==0x342:
                from els_server.protocol.pvp_match_messages import registration_ack
                return [registration_ack(-1,False,'')]
            if kind==0x34a:return []
        if kind==0x7d4 and room is None:return self.registrations.gate(s,event)
        if kind==0x342 and room is None:
            response=self.registrations.register(s,event,sequence)
            if response and response[0].payload[:4]==bytes(4):self.registrations.match()
            return response
        if kind==0x345 and room is None:return self.registrations.cancel(s,event)
        if kind==0x34a and room is None:
            self.loading.admit(s,event,s.port_probe_port)
            return []
        if room is None:
            if kind==0x67 and s.phase=='map_loading' and getattr(s,'pvp_end_payload',None)==event.payload:
                return [dungeon_messages.end_ack()]
            return None
        if not _envelope(event):return []
        self.rounds.timeout(s)
        try:
            if kind==0x6a:
                if room.kind=='practice':
                    if event.payload:raise ValueError('Practice original exit body')
                    response=self.practice.finish(s,b'',ack=False)
                    return response+self.practice.leave(s,event,battle_exit=True)
                # UI exit2 ->D8EE70 sends empty6A;6B only acknowledges it.
                # Actual6C ->316BB70/C90480 returns the departing owner.
                # 67 is the separate result-screen return path.
                if event.payload:raise ValueError('PvP original exit-consent body')
                self.loading.current(s,room);guard=pvp_actor.capture(self.world,s)
                # C90480 rereads its own native slot after1AB4190 updates
                # the room vectors. Retain this receiver's admitted roster
                # until the original self-departure consumer changes scene.
                notice=pvp_loading_messages.departed(s.account.uid,room.slots,loading=room.phase=='loading')
                consent=Event(0x201,kind=0x6b,payload=bytes(4))
                _prepared_boxes((),(consent,notice))
                guard();self.loading.current(s,room)
                return [consent]+self._finish(s,b'',ack=False)+[notice]
            if kind in (0x2ce,0xad):
                for member in room.members:self.loading.current(member,room)
                from els_server.domain.room_summons import handle as player_spawn
                response=player_spawn(self,room,s,event,sequence,pvp=True)
                if response is not None:return response
            if kind==0x91:return self.loading.progress(s,event)
            if kind==0xa7:return self.rounds.death(s,event,sequence)
            if kind==0xaa:return self.rounds.complete(s,event)
            if kind==0x9e:
                if room.phase=='result':return [play.report_ack(0)]
                response=self.rounds.report(s,event,sequence);self._settle(s);return response
            if kind==0x67:
                # DC3B70: original reason, native DA2F50 report, final i32.
                if len(event.payload)<190:raise ValueError('PvP original departure body')
                play.hp_report(event.payload[4:-4])
                return self._finish(s,event.payload)
            if kind==0x225 and room.phase=='result' and event.payload==struct.pack('>iB',s.account.get_location()['map'],0):
                response=self._finish(s,b'',ack=False)
                # The original result screen can return directly through225.
                return response+s.handle(event,sequence)
            if(kind==0x4fb and room.phase=='result'and room.kind=='challenge'
               and room.origins[room.members.index(s)].scene[0]=='guild'):
                from els_server.protocol.guild_agit_messages import entry_request
                entry_request(event.payload)
                response=self._finish(s,b'',ack=False)
                return response+s.handle(event,sequence)
        except (ValueError,sqlite3.Error):
            if kind==0x9e:return [play.report_ack(2005)]
            if kind==0x91:return [pvp_loading_messages.progress_ack(0,2005)]
            raise
        return None

    def periodic(self,s):
        self.duels.periodic(s)
        if self.room(s)is not None:self.rounds.timeout(s)

    def disconnect(self,s):
        self.duels.disconnect(s)
        self.practice.disconnect(s)
        reg=self.registrations;reg.gates.pop(s,None);reg.queue.pop(s,None)
        offer=reg.offers.pop(s,None)
        if offer:
            for ticket in offer.tickets:
                other=ticket.session;reg.offers.pop(other,None);reg.gates.pop(other,None)
                if other is not s and not other.released:other.coop_error='Official opponent disconnected before admission'
        room=self.room(s)
        if room is None:return
        if room.phase in ('active','reporting'):
            self.rounds.leave(s);self._settle(s)
        elif room.phase=='loading':
            for other in room.members:
                if other is not s and not other.released:other.coop_error='Official opponent disconnected during loading'
        self._remove(s)

    def relay_lost(self,s):
        # The native result screen closes its combat relay before its ordinary
        # town-return request. Keep that room until67/225 or game disconnect.
        room=self.room(s)
        if room is None:return
        if room.phase in ('active','reporting'):
            self.rounds.leave(s);self._settle(s)
        elif room.phase=='loading':self.disconnect(s)

    def manifest(self,app,account):return self.loading.manifest(app,account)
    def relay_target(self,app,account,epoch,target):return self.loading.relay_target(app,account,epoch,target)
