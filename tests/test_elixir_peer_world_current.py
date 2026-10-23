"""Peer adapter fixtures only; actual TLS/room evidence remains separate."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from els_server.domain import elixir_peer_sync as peer_sync
from els_server.domain import elixir_flow as flow

class Actor:pass

class ElixirPeerTests(unittest.TestCase):
    def setUp(self):
        self.sent=[];self.source=Actor();self.peer=Actor();self.room=Actor()
        room=self.room;room.phase='active';room.identity=30000
        room.members=(self.source,self.peer);room.leader=self.source
        room.party=dict(run=room,members=room.members,leader=room.leader)
        self.dispatch=SimpleNamespace(room=lambda actor:actor.room,send=lambda actor,events:self.sent.append((actor,events)))
        self.app=SimpleNamespace(world=SimpleNamespace(dungeons=self.dispatch),registry=SimpleNamespace(enabled=lambda _:True))
        self.state=dict(revision=1,rows=[dict(template=710206,start=2000000000,end=2000001800)])
        for n,actor in enumerate(room.members,1):
            actor.application=self.app;actor.room=room;actor.phase='dungeon_active'
            actor.dungeon_substage_synced=True;actor.dungeon_return_pending=False
            actor.coop_error=False;actor.social_overflow=False;actor.identity={'id':n}
            actor.dungeon_id=30000;actor.active_map=0;actor.gate_stage=0
            actor.dungeon_run=SimpleNamespace(run_id='private-peer-fixture',stage=0,part=0,visits=1)
            actor.shop_session_id='fixture-session-'+str(n)
            actor.account=SimpleNamespace(uid=1000+n,account_id=n,store=SimpleNamespace(path='unused-private-fixture'))
            actor._world_elixir_sent=flow.signature(actor,self.state)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(flow,'enabled',return_value=True))
        self.stack.enter_context(patch.object(peer_sync,'_generation',side_effect=lambda room,actor:(actor.gate_stage,actor.dungeon_run.stage,actor.dungeon_run.part,actor.dungeon_run.visits)))
        self.notice=self.stack.enter_context(patch.object(peer_sync.store,'notice',return_value=dict(events=[object()],state=self.state)))
        self.snapshot=self.stack.enter_context(patch.object(peer_sync.store,'snapshot',return_value=self.state))

    def test_same_generation_delivery_once_then_gate_refresh(self):
        self.assertEqual(peer_sync.relay(self.source),1)
        self.assertEqual(peer_sync.relay(self.source),0)
        self.assertEqual(len(self.sent),1)
        self.source.gate_stage=1
        self.source._world_elixir_sent=flow.signature(self.source,self.state)
        self.assertEqual(peer_sync.relay(self.source),0)
        self.peer.gate_stage=1
        self.assertEqual(peer_sync.relay(self.source),1)
        self.assertEqual(len(self.sent),2)

    def test_pending_recipient_and_queue_failure_allow_notice_retry(self):
        self.snapshot.side_effect=ValueError('private pending recipient')
        self.assertEqual(peer_sync.relay(self.source),0);self.assertFalse(self.sent)
        self.snapshot.side_effect=None
        with patch.object(self.dispatch,'send',side_effect=RuntimeError('private queue fault')):
            self.assertEqual(peer_sync.relay(self.source),0)
        self.assertEqual(self.source._world_elixir_peer_error,'RuntimeError')
        self.assertEqual(peer_sync.relay(self.source),1)
        self.assertEqual(len(self.sent),1)

    def test_outside_room_unloaded_and_town_recipient_rejected(self):
        cases=(('room',None),('dungeon_substage_synced',False),('phase','town_ready'),('dungeon_id',30001),('coop_error',True))
        for name,value in cases:
            old=getattr(self.peer,name);setattr(self.peer,name,value)
            self.assertEqual(peer_sync.relay(self.source),0)
            setattr(self.peer,name,old)
        self.assertFalse(self.sent)

if __name__=='__main__':unittest.main()
