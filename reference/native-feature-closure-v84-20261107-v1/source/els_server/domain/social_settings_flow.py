"""Native167 preferences share the authenticated character and SQL boundary."""
import sqlite3
from els_server.domain.friend_flow import capture
from els_server.domain.pvp_registration import _envelope
from els_server.protocol.social_settings_messages import DEFAULT,reply
from els_server.storage import social_settings as storage

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x167:return None
    try:
        guard=capture(s)
        if (not _envelope(event) or type(sequence)is not int or not 1<=sequence<2**32
                or s.phase in('closing','channels_ready')or s.account.store.uid!=s.account.uid):
            raise ValueError('Native social settings actor/envelope')
        return storage.save(s.account.store.path,s.account.uid,s.account.account_id,event.payload,guard)
    except(ValueError,sqlite3.Error):
        return [reply(DEFAULT,1836)]
