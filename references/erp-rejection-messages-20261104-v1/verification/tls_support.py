"""Existing production handlers over private Application/TLS; no online writes."""
import source
from source import HERE,BASE
import asyncio,contextlib,functools,hashlib,importlib.util,json,os,sqlite3,struct
from unittest.mock import patch

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
t=load('prompt_tls_fixture',HERE/'friends_fixture.py')
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.result_messages import result_messages
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer.send=send;load('prompt_tls_reader',HERE/'native_fixture_reader.py').install(t)
