"""Original19C period-service map, key1; other fields retain current defaults."""
from datetime import datetime,timedelta,timezone
import struct
from els_server.protocol.local_messages import login_configuration,wstring,u32
from els_server.protocol.protocol_codec import Event

def deadline_text(epoch):
 if type(epoch)is not int or not 0<=epoch<32503651200:raise ValueError('FishingVIP native date range')
 return datetime.fromtimestamp(epoch,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')if epoch else''

def notice(epoch):
 old=login_configuration()
 if old.kind!=0x19c or old.payload[30:34]!=u32(0):raise ValueError('Original19C period field changed')
 entry=u32(1)+struct.pack('>i',1)+wstring(deadline_text(epoch))
 return Event(old.event_id,kind=old.kind,payload=old.payload[:30]+entry+old.payload[34:])
