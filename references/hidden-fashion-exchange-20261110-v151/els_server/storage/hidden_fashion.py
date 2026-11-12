"""Account-day voucher award, committed by the existing hidden-clear writer."""

from els_server.domain.hidden_fashion import POLICY, VOUCHER
from els_server.domain.raid_reward_items import _issue_source
from els_server.domain.reward_rules import item_plan
from els_server.storage.ariel_attendance import day
from els_server.storage.inventory_state import InventoryFull, grant_items


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS hidden_fashion_days (
        account_id INTEGER NOT NULL, day INTEGER NOT NULL,
        run_id TEXT NOT NULL UNIQUE REFERENCES reward_receipts(run_id),
        voucher_uid INTEGER NOT NULL,
        PRIMARY KEY(account_id, day))''')


def voucher_uid(db, account_id, run_id):
    row = db.execute('SELECT voucher_uid FROM hidden_fashion_days WHERE account_id=? AND run_id=?',
                     (account_id, run_id)).fetchone()
    return row[0] if row else None


def award(db, account_id, owner, run_id, moment, guard):
    current_day = day(int(moment))
    last_day = db.execute('SELECT MAX(day) FROM hidden_fashion_days WHERE account_id=?', (account_id,)).fetchone()[0]
    if last_day is not None and last_day >= current_day:
        return None

    def authority(writer):
        guard()
        return writer is db

    plan = [item_plan(VOUCHER, 1)]
    db.execute('SAVEPOINT hidden_fashion_voucher')
    try:
        source = _issue_source(db, owner, run_id + ':hidden-fashion', 'ordinary',
                               {'policy': POLICY, 'run_id': run_id, 'account_id': account_id, 'day': current_day},
                               plan, authority)
        voucher, = grant_items(db, plan, owner, raid_reward_source=source)
        db.execute('INSERT INTO hidden_fashion_days VALUES (?,?,?,?)',
                   (account_id, current_day, run_id, voucher['uid']))
    except InventoryFull:
        # The original clear still settles. Freeing a slot lets the next clear award the voucher.
        db.execute('ROLLBACK TO hidden_fashion_voucher')
        db.execute('RELEASE hidden_fashion_voucher')
        return None
    db.execute('RELEASE hidden_fashion_voucher')
    return voucher['uid']
