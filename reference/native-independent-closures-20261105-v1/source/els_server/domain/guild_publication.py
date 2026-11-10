"""Lock recipients of the existing invite, admission and appearance producers."""
from contextlib import closing
from pathlib import Path
import sqlite3,struct


def targets(s,function,args):
    if(s.role!='game'or 0x28 not in s.completed
       or s.application.playing.get(s.identity['id'])is not s):return ()
    from els_server.protocol.protocol_codec import Event
    event=args[0]if function.__name__=='handle'and len(args)==1 and type(args[0])is Event else None
    kind=event.kind if event is not None and event.event_id==0x202 else None
    context=getattr(s,'guild_agit',None)
    if context is None:
        if kind in(0x709,0x4e2,0x506,0x7e0):
            from els_server.domain.luciel_state import peers
            return tuple(peers(s)[1])
        if kind not in(0x285,0x288,0x4fb):return ()
    path=Path(s.account.store.path).resolve()
    live=tuple(p for p in tuple(s.application.playing.values())if not p.released
        and p.role=='game'and p.phase not in('closing','channels_ready')
        and p.identity['id']==p.account.account_id and Path(p.account.store.path).resolve()==path)
    result=set()
    if context is not None:
        result.update(p for p in live if getattr(p,'guild_agit',None)is not None
                      and p.guild_agit['guild']==context['guild'])
    if event is None or event.event_id!=0x202:return tuple(result)
    extra=()
    if kind==0x285 and len(event.payload)>=8:
        extra=(struct.unpack_from('>Q',event.payload,len(event.payload)-8)[0],)
    elif kind in(0x288,0x4fb):
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db:
            tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if kind==0x288 and 'native_guild_invitations'in tables:
                row=db.execute('SELECT inviter_uid FROM native_guild_invitations WHERE target_uid=?AND target_account=?',
                               (s.account.uid,s.account.account_id)).fetchone()
                if row is not None:extra=row
            elif kind==0x4fb and 'native_guild_members'in tables:
                members=dict(db.execute('SELECT peer.owner,peer.account_id FROM native_guild_members mine '
                    'JOIN native_guild_members peer ON peer.guild_id=mine.guild_id '
                    'WHERE mine.owner=?AND mine.account_id=?',(s.account.uid,s.account.account_id)))
                result.update(p for p in live if members.get(p.account.uid)==p.identity['id']
                              and getattr(p,'guild_agit',None)is not None)
    result.update(p for p in live if p.account.uid in extra)
    return tuple(result)
