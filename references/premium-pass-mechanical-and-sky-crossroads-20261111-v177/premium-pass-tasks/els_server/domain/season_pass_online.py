"""Account pass online objectives from the selected session's committed clock."""
import json
from functools import lru_cache

from els_server.domain import periodic_activities as rules
from els_server.domain.attendance_2026_online import selected_local_test_character
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.protocol.quest_messages import progress
from els_server.storage import periodic_quest_scope as scope
from els_server.storage.read_scope import snapshot_connection


@lru_cache(maxsize=1)
def objectives():
    catalog = rules.catalog()
    result = {}
    for qid in catalog['pass_ids']:
        for sid in rules.definition(qid)['m_vecSubQuest'].values():
            sub = catalog['subquests'].get(str(sid))
            if sub is not None and sub['m_eClearType'] == 102:
                result[qid] = (sid, rules.target(sub))
    return result


def bind(session, rows):
    if any(row['id'] in objectives() for row in rows):
        actor = session.account
        session._season_pass_online_actor = (session.shop_session_id, actor.account_id, actor.uid)


class SeasonPassOnlineClock(OnlineTitleClock):
    def __init__(self, *, monotonic, epoch):
        super().__init__(None, campaign='season-pass', eligibility=self._eligible,
                         monotonic=monotonic, epoch=epoch)

    def _eligible(self, session):
        actor = session.account
        expected = (session.shop_session_id, actor.account_id, actor.uid)
        if (getattr(session, '_season_pass_online_actor', None) == expected
                and rules.active_season(int(self.epoch())) is not None):
            return selected_local_test_character(session)
        return None

    def _write_spans(self, db, account, character, start, end):
        scope.account(db, character, account)
        definitions = objectives()
        for qid, accepted, _, raw in scope.active_rows(db, character, quest_ids=definitions.keys()):
            sid, limit = definitions[qid]
            counts = json.loads(raw)
            if counts[str(sid)] == limit:
                continue
            season = rules.active_season(accepted)
            if season is None:
                continue
            repeat = rules.definition(qid)['m_eRepeatType']
            window = rules.period(accepted, repeat)
            finish = min(end, season[1], window + (86400 if repeat == 1 else 604800))
            begin = max(start, accepted)
            if finish <= begin:
                continue
            db.execute('''CREATE TABLE IF NOT EXISTS season_pass_online_v1(
                account INTEGER NOT NULL, quest INTEGER NOT NULL, period INTEGER NOT NULL,
                seconds INTEGER NOT NULL, observed_until INTEGER NOT NULL,
                PRIMARY KEY(account, quest))''')
            row = db.execute('SELECT seconds,observed_until FROM season_pass_online_v1 '
                             'WHERE account=? AND quest=? AND period=?', (account, qid, window)).fetchone()
            seconds, observed_until = row if row else (0, begin)
            added = finish - max(begin, observed_until)
            if added <= 0:
                continue
            seconds = min(60 * limit, seconds + added)
            db.execute('''INSERT INTO season_pass_online_v1 VALUES(?,?,?,?,?)
                ON CONFLICT(account,quest) DO UPDATE SET period=excluded.period,
                    seconds=excluded.seconds,observed_until=excluded.observed_until''',
                       (account, qid, window, seconds, finish))
            minutes = seconds // 60
            if minutes > counts[str(sid)]:
                counts[str(sid)] = minutes
                scope.update_objectives(db, character, qid, counts)

    def notices(self, session):
        now = int(self.epoch())
        next_projection, published = getattr(session, '_season_pass_online_projection', (0, ()))
        if self.identity is None or now < next_projection:
            return []
        path, account, character, _ = self.identity
        if self.identity != self._eligible(session):
            return []
        with snapshot_connection(path) as db:
            rows = []
            seen = set()
            for qid, accepted, generation, raw in scope.active_rows(db, character, quest_ids=objectives().keys()):
                if not rules.visible(qid, accepted, now, active=True):
                    continue
                counts = {int(key): value for key, value in json.loads(raw).items()}
                key = (account, character, qid, generation, tuple(counts.items()))
                seen.add(key)
                if any(counts.values()) and key not in published:
                    rows.append(dict(id=qid, owner=character, accepted_at=accepted,
                                     generation=generation, objectives=counts))
        session._season_pass_online_projection = (now + 15, seen)
        return [progress(rows)] if rows else []
