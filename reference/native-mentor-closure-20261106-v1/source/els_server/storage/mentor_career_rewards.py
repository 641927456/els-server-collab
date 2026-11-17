"""First/second advancement proof, sealed in the original career writer."""
import time
from els_server.domain.character_rules import CLASSES
from els_server.storage import mentor_relations as relations


def recipient(db,mail_id):
    if not relations.exists(db,'native_mentor_career_rewards'):return None
    row=db.execute('SELECT teacher FROM native_mentor_career_rewards WHERE mail_id=?',(mail_id,)).fetchone()
    return None if row is None else row[0]


def issue(db,before,after):
    stage=CLASSES[after['unit_class']]['stage']
    if stage not in(1,2)or CLASSES[before['unit_class']]['stage']!=stage-1:return None
    if not db.in_transaction:raise ValueError('Mentor proof requires original career writer')
    student=after['uid'];saved=relations.relation(db,student)
    if saved is None or not saved['is_student']or before['level']>=99:return None
    teacher=saved['partner'];account=relations.character(db,uid=teacher)['account_id']
    # This is passive character-owned mail, not an action by its recipient.
    # A teacher's pending deletion must not block the student's advancement;
    # final deletion already retires the relation in its original writer.
    relations.require_owner(db,teacher,account)
    from els_server.storage.game_mail import ensure
    ensure(db)
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_career_rewards(
        student INTEGER NOT NULL REFERENCES characters(uid),stage INTEGER NOT NULL,
        generation TEXT NOT NULL,teacher INTEGER NOT NULL REFERENCES characters(uid),
        mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),PRIMARY KEY(student,stage))''')
    # Re-selection and any future route reset never mint the same student's
    # first/second advancement proof twice, even with a later teacher.
    if db.execute('SELECT 1 FROM native_mentor_career_rewards WHERE student=?AND stage=?',(student,stage)).fetchone():return None
    template=189802 if stage==1 else 189803
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
    from els_server.storage.item_instances import next_uid
    from els_server.storage.mail_attachments import put
    from els_server.storage.player_mail import ORDINARY_RETENTION,decorate
    from els_server.protocol.mail_attachment_messages import header,detail
    from els_server.game_data import client_data
    now=int(time.time());name=client_data().item(template)['name']
    mid=db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)
        VALUES(?,?,?,?,?,0,?,?)''',(f'mentor-career-{student}-{stage}',account,'阿莉尔',name,
        f'你的徒弟完成了{stage}转，请领取师徒任务证明。',now,now+ORDINARY_RETENTION)).lastrowid
    db.execute('INSERT INTO native_mentor_career_rewards VALUES(?,?,?,?,?)',
        (student,stage,saved['generation'],teacher,mid))
    item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],
        group=TEMPLATE_BAG_GROUPS[template],slot=0,count=1))
    item_body(item);put(db,mid,item,item)
    cur=db.execute('SELECT *FROM game_mail WHERE id=?',(mid,))
    row=decorate(db,dict(zip((c[0]for c in cur.description),cur.fetchone())),now=now)
    header(row);detail(row)
    return mid
