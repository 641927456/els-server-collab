"""Opt-in authenticated originalD2C/D29/610/D3/D2D participation sequence.

Only committed state is returned; no GM join or client-selected account/UID.
New profile construction is the explicit local policy supplied at startup.
This standalone campaign does not activate the other pending activity routes.
"""
from contextlib import closing
import sqlite3,uuid
from els_server.storage.boosting_2026_complete_join import CompleteJoinedParticipation
from els_server.storage.inventory_state import InventoryFull
from els_server.protocol import boosting_2026_join as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol.resonance_2026 import ResonanceState
from els_server.domain.dungeon_drops import pickup_inventory_notice


class BoostingJoinFlow:
    online=None
    def __init__(self,original,curve,catalog,stats,*,clock,campaign_open,new_profile_policy):
        self.original,self.curve,self.catalog,self.stats=original,curve,catalog,stats
        self.clock,self.campaign_open,self.profile_policy=clock,campaign_open,new_profile_policy
        self.token=uuid.uuid4().hex;self.last=None

    def _store(self,db):return CompleteJoinedParticipation(db,self.original,self.curve,self.catalog,self.stats,new_profile_policy=self.profile_policy)

    @staticmethod
    def enabled(s):
        return (s.role=='game' and s.client_build=='dx11_260923' and s.item_test and s.account.characters is not None
            and s.account.store is not None and not getattr(s,'released',False))

    def capture(self,s):pass
    def prepare_clear(self,s):return None

    def handle(self,s,event,sequence):
        if event.event_id!=0x202 or event.kind!=0xd2c or not self.enabled(s):return None
        fail=lambda result=681:[wire.participation_reply(result=result)]
        if (s.phase!='town_ready' or type(sequence) is not int or not 1<=sequence<2**32 or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return fail()
        try:
            wire.participation_request(event.payload)
            messages=[]
            with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
                db.execute('BEGIN IMMEDIATE');t=self._store(db);now=self.clock()
                def encode(out):
                    messages[:]=[wire.binding_notice(character_uid=out['binding'].character_uid),out['profile'].notice()]
                    if out['updates']:messages.append(pickup_inventory_notice(out['updates']))
                    messages.append(wire.participation_reply(result=0))
                    return b''.join(encode_event(e) for e in messages)
                out=t.join(account=s.account.account_id,character=s.account.uid,operation=f'join:{self.token}:{sequence}',now=now,
                    campaign_open=self.campaign_open(s,now),encode=encode)
            self.last=(s.account.uid,out['binding'].character_uid,out['profile'].notice().payload)
            return messages
        except InventoryFull:return fail(165)
        except ValueError:return fail()

    def finalize(self,s,replies):
        if not self.enabled(s) or getattr(s,'reward_transaction',None) is not None:return replies
        restoring=any(e.event_id==0x201 and e.kind in (0x2a,0x2b) for e in replies)
        if s.phase not in ('town_ready','dungeon_active') and not restoring:return replies
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            t=self._store(db);t._owner_level(s.account.account_id,s.account.uid)
            bound=t._read(s.account.account_id);uid=bound.character_uid if bound else 0
        signature=(s.account.uid,uid);out=list(replies)
        if restoring or signature!=self.last:out.append(wire.binding_notice(character_uid=uid))
        self.last=signature
        return out
