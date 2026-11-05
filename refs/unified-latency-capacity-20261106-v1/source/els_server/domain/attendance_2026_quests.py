"""Explicit local-test session adapter for the selected pending daily task.

Attach to an injected clear binding as .quests. Default sessions never create
this adapter. Missing rewards stay unavailable; online observations must be supplied by a verified timer.
"""
import sqlite3
import struct
from contextlib import closing
from els_server.protocol import attendance_2026_quest as wire
from els_server.protocol import quest_messages as ordinary
from els_server.protocol.protocol_codec import Event
from els_server.storage.attendance_2026_progress import AttendanceProgress
from els_server.storage.attendance_2026_tasks import AttendanceTasks


class AttendanceQuestBinding:
    def __init__(self, definition, *, campaign, definition_sha256, schedule, clock):
        self.definition,self.campaign,self.digest=definition,campaign,definition_sha256
        self.schedule,self.clock=schedule,clock
        self.last=None

    def _state(self, s, operation):
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            p=AttendanceProgress(db,self.definition,campaign_id=self.campaign,definition_sha256=self.digest)
            task=AttendanceTasks(p,self.schedule)
            return getattr(task,operation)(account=s.account.account_id,character=s.account.uid,now=self.clock())

    @staticmethod
    def enabled(s):
        return (s.role=='game' and s.client_build=='dx11_260923' and s.item_test
                and s.account.characters is not None and s.account.store is not None
                and not getattr(s,'released',False))

    @staticmethod
    def view(state,*,owner_uid):
        seconds=state['online_seconds']
        if type(seconds) is not int or not 0<=seconds<=3600:
            raise ValueError('Invalid authoritative online seconds')
        # Original type102 text is 60 minutes and native CFD220 forwards its
        # counter unchanged to the formatter. This conversion does not decide
        # which scenes count as online or create observations by itself.
        return dict(owner_uid=owner_uid,clears=state['clears'],
                    online_count=seconds//60,online_complete=seconds==3600)

    def handle(self, s, event, sequence):
        if (event.event_id!=0x202 or event.kind not in (0xee,0xfa,0xf4)
                or len(event.payload)<4 or struct.unpack_from('>i',event.payload)[0]!=166210
                or not self.enabled(s)):
            return None
        def failure(result=2005):
            if event.kind==0xee:return [ordinary.accept_ack(-1)]
            if event.kind==0xfa:
                from els_server.domain.quest_flow import initialization
                return [initialization(s)] # no abandonment; restore the preserved map
            inv=s.account.get_inventory_snapshot()
            return [ordinary.reward_ack(166210,s.account.character(),s.account.get_location(),s.account.get_skills(),inv['balances'],inv['items'],result=result)]
        if (s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers!=(0,) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            return failure()
        try:
            request=ordinary.request(event.kind,event.payload)
            if request.get('npc',0)!=0:raise ValueError('Selected task has no NPC')
            if event.kind==0xee:
                state=self._state(s,'accept');view=self.view(state,owner_uid=s.account.uid)
                self.last=(s.account.uid,state['accepted_at'],tuple(view.items()))
                return [ordinary.accept_ack(),wire.accepted(**view)]
            if event.kind==0xfa:return failure()
            result=self._state(s,'claim')
            return failure(result['result'])
        except ValueError:return failure()

    def finalize(self, s, replies):
        if not self.enabled(s):return replies
        if (s.phase not in ('town_ready','dungeon_active')
                and not any(e.kind==0x2b and e.event_id==0x201 for e in replies)):
            return replies
        character=s.account.character()
        if character is None or character['level']<self.definition.minimum_level:return replies
        state=self._state(s,'snapshot')
        if state is None:return replies
        view=self.view(state,owner_uid=s.account.uid);signature=(s.account.uid,state['accepted_at'],tuple(view.items()))
        # Each 2B is a replacement map. Merge the pending task into each one,
        # preserving the ordinary records byte-for-byte after the header.
        out=[];restored=False
        for event in replies:
            if event.kind==0x2b and event.event_id==0x201:
                payload=event.payload
                if len(payload)<20 or payload[:4]!=bytes(4):raise ValueError('Unexpected ordinary quest initialization')
                count=struct.unpack_from('>I',payload,4)[0]
                payload=payload[:4]+struct.pack('>I',count+1)+wire.active_record(**view)+payload[8:]
                out.append(Event(0x201,kind=0x2b,payload=payload));restored=True
            else:out.append(event)
        if not restored and any(e.kind in (0xd9,0x29f) for e in replies):
            from els_server.domain.quest_flow import initialization
            return self.finalize(s,out+[initialization(s)])
        if not restored and signature!=self.last and not any(e.kind==0xf0 and e.payload[:4]==struct.pack('>i',166210) for e in replies):
            out.append(wire.progress(**view))
        self.last=signature
        return out
