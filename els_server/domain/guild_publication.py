"""Hold actual recipients before SQL writers and prepared mailbox adoption."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct

def guild_peers(s,extra=()):
    from els_server.storage.guild_system_state import exists
    path=Path(s.account.store.path).resolve()
    with closing(sqlite3.connect(path))as db:
        rows=dict(db.execute('SELECT peer.owner,peer.account_id FROM native_guild_members mine '
            'JOIN native_guild_members peer ON peer.guild_id=mine.guild_id '
            'WHERE mine.owner=?AND mine.account_id=?',(s.account.uid,s.account.account_id)))if exists(db,'native_guild_members')else{}
    return tuple(p for p in tuple(s.application.playing.values())
        if not p.released and p.role=='game'and p.phase not in('closing','channels_ready')
        and p.identity['id']==p.account.account_id and Path(p.account.store.path).resolve()==path
        and (rows.get(p.account.uid)==p.identity['id']or p.account.uid in extra))

def targets(s,function,args):
    """Select notification receivers before the worker takes any mailbox lock."""
    if(s.role!='game'or 0x28 not in s.completed
       or s.application.playing.get(s.identity['id'])is not s):return ()
    result=set();context=getattr(s,'guild_agit',None)
    if context is not None:
        result.update(p for p in tuple(s.application.playing.values())
            if getattr(p,'guild_agit',None)is not None and p.guild_agit['guild']==context['guild']
            and not p.released)
    from els_server.protocol.protocol_codec import Event
    event=args[0]if function.__name__=='handle'and len(args)==1 and type(args[0])is Event else None
    if event is None or event.event_id!=0x202:return tuple(result)
    kind=event.kind;extra=()
    if kind in(0x709,0x4e2,0x506,0x7e0):
        if context is None:
            from els_server.domain.luciel_state import peers
            result.update(peers(s)[1])
    if kind==0x285 and len(event.payload)>=8:extra=(struct.unpack_from('>Q',event.payload,len(event.payload)-8)[0],)
    elif kind==0x2ca and len(event.payload)==8:extra=(struct.unpack('>Q',event.payload)[0],)
    elif kind==0x288:
        from els_server.storage.guild_system_state import exists
        with closing(sqlite3.connect(s.account.store.path))as db:
            row=db.execute('SELECT inviter_uid FROM native_guild_invitations WHERE target_uid=?AND target_account=?',
                (s.account.uid,s.account.account_id)).fetchone()if exists(db,'native_guild_invitations')else None
        extra=()if row is None else(row[0],)
    from els_server.domain.guild_system_flow import KINDS,READS
    guild_command=kind in KINDS-READS
    if kind==0x219:
        guild_command=False
        if len(event.payload)>=8:
            from els_server.storage.inventory_state import owned_template
            from els_server.domain.guild_consumables import TEMPLATES
            with closing(sqlite3.connect(s.account.store.path))as db:
                guild_command=owned_template(db,s.account.uid,struct.unpack_from('>Q',event.payload)[0])in TEMPLATES
    if kind==0xe44:guild_command=event.payload[-4:]==struct.pack('>i',25)
    if(guild_command or kind in(0x285,0x288,0x2ca)
       or kind==0x85 and event.payload[:1]==b'\3'):
        result.update(guild_peers(s,extra))
    elif kind==0x4fb:
        result.update(p for p in guild_peers(s)if getattr(p,'guild_agit',None)is not None)
    return tuple(result)
