"""Source185080 / AC effect39: native20percent to the owned ridden mount.

The original115 applies its native visual effect once. This hook persists the
same capped amount in the original consumable inventory/cooldown transaction.
"""
def apply(db,owner,now):
    from els_server.storage.mount_state import owned,settle
    from els_server.domain.mount_rules import template,f32
    if not db.in_transaction:raise ValueError('Mount fuel requires original item writer')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='companion_active'").fetchone():raise ValueError('Mount fuel requires actual ridden mount')
    row=db.execute('SELECT mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone()
    if not row or not row[0] or row[1]!=1:raise ValueError('Mount fuel requires actual ridden mount')
    mount=settle(db,owner,owned(db,owner,row[0]),now)
    if(not mount['ridden'] or mount.get('expires_at',now+1)<=now
       or db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_race_busy'").fetchone()
       and db.execute('SELECT 1 FROM mount_race_busy WHERE uid=?',(mount['uid'],)).fetchone()):raise ValueError('Mount fuel current ride unavailable')
    maximum=float(template(mount['unit'])['max_stamina'])
    # D7E790: truncate(FLOAT32(FLOAT32(amount/100)*maximum)), then add.
    restored=int(f32(f32(f32(20.)/100.)*maximum))
    value=min(maximum,f32(mount['stamina']+restored))
    if db.execute('UPDATE mount_runtime SET stamina=?WHERE owner=?AND uid=?AND ridden=1',(value,owner,mount['uid'])).rowcount!=1:raise ValueError('Mount fuel ride changed')
