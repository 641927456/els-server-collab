"""Account progress and permanent outfit entitlement from observed online time."""
from els_server.domain.anniversary_promotion import BOXES, ENDS, MAIL_DEADLINE, REQUIRED_SECONDS, STARTS, mail_key
from els_server.domain.anniversary_exchange import MAIL_PREFIX, MAX_COUPONS, SECONDS_PER_COUPON, TOKEN


def awarded(db, account):
    return db.execute('SELECT 1 FROM game_mail WHERE account_id=? AND campaign=?',
                      (account, mail_key(BOXES[0]))).fetchone() is not None


def coupons_issued(db, account):
    return db.execute('''SELECT COALESCE(MAX(CAST(SUBSTR(campaign, ?) AS INTEGER)),0)
        FROM game_mail WHERE account_id=? AND campaign GLOB ?''',
        (len(MAIL_PREFIX) + 1, account, MAIL_PREFIX + '*')).fetchone()[0]


def owns_box(db, account, item):
    return db.execute('''SELECT 1 FROM game_mail m JOIN player_mail_items a ON a.mail_id=m.id
        WHERE m.account_id=? AND m.campaign=? AND a.item_uid=? AND a.claimed_at IS NOT NULL''',
        (account, mail_key(item['template']), item['uid'])).fetchone() is not None


def record_online(db, *, account, character, start, end):
    first, last = max(start, STARTS), min(end, ENDS)
    if first >= last or end >= MAIL_DEADLINE:
        return
    issued = coupons_issued(db, account)
    if issued == MAX_COUPONS:
        return
    level = db.execute('''SELECT c.level FROM characters c JOIN character_owners o ON o.uid=c.uid
        WHERE c.uid=? AND o.account_id=?''', (character, account)).fetchone()
    if level is None or level[0] < 99:
        raise ValueError('Anniversary online time requires an owned level 99 character')

    db.execute('''CREATE TABLE IF NOT EXISTS anniversary_promotion_spans (
        account INTEGER NOT NULL, starts INTEGER NOT NULL, ends INTEGER NOT NULL,
        PRIMARY KEY(account, starts), CHECK(starts<ends))''')
    overlap = 'account=? AND ends>=? AND starts<=?'
    key = (account, first, last)
    previous_first, previous_last = db.execute(
        f'SELECT MIN(starts), MAX(ends) FROM anniversary_promotion_spans WHERE {overlap}', key).fetchone()
    if previous_first is not None:
        db.execute(f'DELETE FROM anniversary_promotion_spans WHERE {overlap}', key)
        first, last = min(first, previous_first), max(last, previous_last)
    db.execute('INSERT INTO anniversary_promotion_spans VALUES (?,?,?)', (account, first, last))
    seconds = db.execute('SELECT SUM(ends-starts) FROM anniversary_promotion_spans WHERE account=?',
                         (account,)).fetchone()[0]
    from els_server.storage.career_rewards import send_items
    if seconds >= REQUIRED_SECONDS and not awarded(db, account):
        send_items(db, account, character, BOXES, campaign=mail_key, now=end, deadline=MAIL_DEADLINE,
                   subject='15周年庆·三转晋级时装',
                   body='累计在线60分钟奖励。领出的箱子和开出的时装均永久有效。三转及以上角色可开启。')
    reached = min(seconds // SECONDS_PER_COUPON, MAX_COUPONS)
    if reached > issued:
        send_items(db, account, character, (TOKEN,), campaign=lambda _: f'{MAIL_PREFIX}{reached}',
                   now=end, deadline=MAIL_DEADLINE, item_deadline=MAIL_DEADLINE, quantity=reached - issued,
                   subject=f'15周年庆·感恩券（累计在线{reached * 10}分钟）',
                   body='请在活动期间前往阿莉尔的兑换菜单，每张券可选择兑换一项周年庆奖励。')
    if reached == MAX_COUPONS:
        db.execute('DELETE FROM anniversary_promotion_spans WHERE account=?', (account,))
