"""Cold-clear recovery extension of the sealed local session binding."""
from contextlib import closing
import sqlite3,struct
from els_server.domain.boosting_2026_quests import BoostingQuestBinding
from els_server.storage.boosting_2026_recovery import RecoverableRewards
from els_server.protocol import boosting_2026_quest as wire
from els_server.protocol import quest_messages as ordinary


class RecoveringBoostingQuestBinding(BoostingQuestBinding):
    def _store(self,db):return RecoverableRewards(db,self.original)

    def _recover(self,s):
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            if not self._participant(db,s):return None
            row=self._store(db).recover_clears(account=s.account.account_id,character=s.account.uid)
            # Encode before committing counter/marker; callers emit only after
            # the connection context has successfully committed.
            message=wire.progress(self.definition,row,owner_uid=s.account.uid) if row else None
        return message

    def handle(self,s,event,sequence):
        # Recover before deciding whether an authenticated claim is ready.
        # Malformed/foreign envelopes cannot trigger this write path.
        recovered=None
        if (self.enabled(s) and s.phase=='town_ready' and event.event_id==0x202 and event.kind==0xf4
                and type(sequence) is int and 1<=sequence<2**32 and event.performers==(0,)
                and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0):
            try:request=ordinary.request(0xf4,event.payload)
            except ValueError:request=None
            if request is not None and request['quest'] in self.quests:
                q=self.quests[request['quest']]
                if request['npc'] in (0,q['m_eEndNPCID'],10025):recovered=self._recover(s)
        answer=super().handle(s,event,sequence)
        if recovered is not None and answer is not None:
            completed=any(e.event_id==0x201 and e.kind==0xf5 and e.payload[:4]==bytes(4) for e in answer)
            if not completed:answer.append(recovered)
        return answer

    def finalize(self,s,replies):
        if not self.enabled(s):return replies
        has_restore=any(e.event_id==0x201 and e.kind==0x2b for e in replies)
        if s.phase not in ('town_ready','dungeon_active') and not has_restore:return replies
        message=self._recover(s)
        out=super().finalize(s,replies)
        # A2B already includes the recovered count; otherwise notify the client
        # once with F3. Repeated periodic calls find no unconsumed eligible run.
        if message is not None and not has_restore:out.append(message)
        return out
