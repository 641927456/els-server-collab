"""Account character identities and transactional creation receipts."""

import hashlib

import json

import sqlite3

import unicodedata

from els_server.domain.player_name_rules import is_alnum,column_width

from contextlib import closing

from pathlib import Path

from els_server.storage.character_schema import character_uid,migrate_character_schema

from els_server.storage.sqlite_timing import write_transaction



# Current client's UNIT_CLASS / UNIT_TYPE enums, also used by the native

# CorrelateUnitClassTemplet. Character type is not a class ID for types 10–15.

BASE_CLASSES={**{n:n for n in range(1,10)},10:200,11:201,12:202,13:203,14:204,15:205}

DEFAULT_CHARACTER=dict(uid=1001,name='LocalElsword',unit_type=1,unit_class=1,

                       level=1,transcendence=False,master=False,revision=0,skill_row_expanded=False,bag_capacities={},skill_seal_groups=())



def validate_name(name):

    if not isinstance(name,str) or not 2<=len(name)<=12:

        raise ValueError('Character name length')

    if sum(column_width(c) for c in name)>12:raise ValueError('Character name length')

    if len(name.encode('utf-16le'))>24 or any(not is_alnum(c) for c in name):

        raise ValueError('Character name characters')

    if unicodedata.normalize('NFC',name)!=name:raise ValueError('Noncanonical character name')

    return name



def prepare_character_catalogs():

    # Immutable SHA-checked native evidence; never inspect a player database.

    from els_server.domain.equipment_eligibility import catalog as wear_catalog

    from els_server.domain.equipment_instance import restricted_templates

    from els_server.domain.role_progression import catalog as role_catalog

    from els_server.domain.equipment_requirements import catalog as equipment_catalog

    from els_server.domain.seal_quests import quest_catalog

    from els_server.domain.local_artifact_rules import generation

    from els_server.domain.skill_traits import catalog as trait_catalog

    wear_catalog();restricted_templates();role_catalog();equipment_catalog();quest_catalog();generation();trait_catalog()





class Characters:

    def __init__(self,path,account_id=1):

        if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Invalid account identity')

        self.account_id=account_id

        self.path=Path(path)

        from els_server.storage.initialization_checks import read_ready,characters_ready

        with closing(sqlite3.connect(self.path,timeout=10)) as db:

            if not read_ready(db,characters_ready):

                with write_transaction(db):

                    migrate_character_schema(db)

                    db.execute('CREATE TABLE IF NOT EXISTS characters (uid INTEGER PRIMARY KEY CHECK(uid>=1001), name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, unit_type INTEGER NOT NULL CHECK(unit_type BETWEEN 1 AND 15), unit_class INTEGER NOT NULL, level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99), transcendence INTEGER NOT NULL CHECK(transcendence IN (0,1)), master INTEGER NOT NULL CHECK(master IN (0,1)), revision INTEGER NOT NULL DEFAULT 0)')

                    # Preserve the original character schema and every legacy row.

                    # Only previously unowned roles are adopted by the local account.

                    db.execute('CREATE TABLE IF NOT EXISTS character_owners (uid INTEGER PRIMARY KEY REFERENCES characters(uid), account_id INTEGER NOT NULL CHECK(account_id>0))')

                    db.execute('INSERT OR IGNORE INTO character_owners SELECT uid,1 FROM characters')

                    db.execute('CREATE INDEX IF NOT EXISTS character_owners_account ON character_owners(account_id)')

                    db.execute('CREATE TABLE IF NOT EXISTS character_creation_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, uid INTEGER NOT NULL REFERENCES characters(uid))')

                    db.execute('CREATE TABLE IF NOT EXISTS character_artifacts (uid INTEGER PRIMARY KEY REFERENCES characters(uid), template INTEGER NOT NULL CHECK(template BETWEEN 1 AND 15), evolution INTEGER NOT NULL CHECK(evolution BETWEEN 1 AND 5), level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99), experience INTEGER NOT NULL CHECK(experience>=0), potentials TEXT NOT NULL)')



    @staticmethod

    def _row(row):

        if row is None:raise ValueError('Unknown character')

        out=dict(zip(('uid','name','unit_type','unit_class','level','transcendence','master','revision'),row))

        out['transcendence']=bool(out['transcendence']);out['master']=bool(out['master'])

        return out



    def list(self):

        return self._project()



    def _project(self,uid=None):

        # Share the full wire projection, but read only the requested owned

        # identity for get(). No player state survives this connection.

        from els_server.storage.erp_support_quest_scope import _table_snapshot

        with snapshot_connection(self.path)as db:

            if not db.in_transaction:db.execute('BEGIN')

            with _table_snapshot(db):return self._project_rows(db,uid)



    def _project_rows(self,db,uid):

        query='SELECT c.uid,name,unit_type,unit_class,level,transcendence,master,revision,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE o.account_id=?'

        parameters=(self.account_id,)

        if uid is not None:

            query+=' AND c.uid=?';parameters+=(uid,)

        rows=[dict(self._row(r[:-1]),account_id=r[-1]) for r in db.execute(query+' ORDER BY c.uid',parameters)]

        if any(type(r['account_id'])is not int or r['account_id']!=self.account_id for r in rows):raise ValueError('Native Unit SQL account identity')

        from els_server.storage.character_lifecycle import decorate

        rows=decorate(db,rows)

        artifact_query='SELECT a.uid,a.template,a.evolution,a.level,a.experience,a.potentials FROM character_artifacts a JOIN character_owners o ON o.uid=a.uid WHERE o.account_id=?'

        if uid is not None:artifact_query+=' AND a.uid=?'

        visible={r['uid'] for r in rows}

        artifacts={r[0]:dict(template=r[1],evolution=r[2],level=r[3],experience=r[4],potentials=json.loads(r[5])) for r in db.execute(artifact_query,parameters) if r[0] in visible}

        from els_server.storage.character_projection import skill_trait_fields,force_fields,skill_page_fields,cleared_dungeons,profession_fields

        has_dungeon_records=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dungeon_records'").fetchone() is not None

        from els_server.storage.achievements import statuses as achievement_statuses

        achievement_views=achievement_statuses(db,self.account_id,visible)

        for row in rows:

            from els_server.storage.life_stamina import snapshot as life_snapshot

            row['life_stamina']=life_snapshot(db,row['uid'],self.account_id)

            from els_server.domain.normal_fatigue_rules import enabled as normal_fatigue_enabled

            if normal_fatigue_enabled():

                from els_server.storage.normal_fatigue import snapshot as normal_fatigue_snapshot

                row['normal_fatigue']=normal_fatigue_snapshot(db,row['uid'],self.account_id)

            from els_server.storage.resonance_state import snapshot as resonance_snapshot

            row['resonance']=resonance_snapshot(db,row['uid'],self.account_id)

            row['achievement_status']=achievement_views[row['uid']]

            from els_server.storage.relationships import snapshot as relationship_snapshot

            row['relationship']=relationship_snapshot(db,row['uid'],self.account_id)

            from els_server.storage.el_search_collection import snapshot as collection_snapshot

            collection=collection_snapshot(db,row['uid'],self.account_id)

            if collection is not None:row['el_search_collection']=collection

            from els_server.storage.titles import equipped as equipped_title,completed_for_equipment

            row['title']=equipped_title(db,row['uid'])

            from els_server.storage.character_custom import actor_snapshot as custom_snapshot

            row['character_custom']=custom_snapshot(db,row['uid'],self.account_id)

            row['title_completed_quests']=completed_for_equipment(db,row['uid'])

            row['artifact']=artifacts.get(row['uid'])

            row['cleared_dungeons']=cleared_dungeons(db,row['uid'],has_records=has_dungeon_records)

            from els_server.storage.ep_points import balance as ep_balance

            ep=ep_balance(db,row['uid'])

            if ep:row['ep']=ep

            from els_server.storage.skill_expansion import is_expanded

            row['skill_row_expanded']=is_expanded(db,row['uid'])

            from els_server.storage.skill_unlocks import saved_groups

            row['skill_seal_groups']=saved_groups(db,row['uid'])

            row.update(skill_trait_fields(db,row,include_empty=False))

            # Every complete Unit producer, including account rosters,

            # reads both independent Force sources in this SQL snapshot.

            row.update(force_fields(db,row['uid']))

            row.update(skill_page_fields(db,row['uid'],include_single=False))

            from els_server.storage.bag_capacity import saved_capacities

            row['bag_capacities']=saved_capacities(db,row['uid'])

            row.update(profession_fields(db,row['uid'],self.account_id))

            if row['unit_type']==10:

                from els_server.storage.luciel_state import state as luciel_state,active_state as luciel_active_state

                row['luciel_style']=luciel_state(db,row['uid'])['style']

                row['luciel_active_unit']=luciel_active_state(db,row['uid'])['active_unit']

        return rows



    def first_identity(self):

        # Session admission only needs the first visible owned UID. Full

        # extended character fields remain in the original wire list/get.

        from els_server.storage.character_lifecycle import visible_ids

        with snapshot_connection(self.path) as db:

            db.execute('BEGIN')

            uids=visible_ids(db,self.account_id)

            return self._identity(db,uids[0]) if uids else None



    def identity(self,uid):

        # Eligibility consumers require current owned identity/level only.

        # Keep all extended projections in get()/list() for wire consumers.

        uid=character_uid(uid)

        from els_server.storage.read_scope import snapshot_connection

        with snapshot_connection(self.path) as db:

            return self._identity(db,uid)



    def _identity(self,db,uid):

        row=db.execute('SELECT c.uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(uid,self.account_id)).fetchone()

        value=self._row(row)

        value['account_id']=self.account_id

        # list()/get() also reject finalized deletions; narrow readers keep

        # the same owner and finalized-character eligibility boundary.

        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_lifecycle'").fetchone():

            state=db.execute('SELECT finalized_at FROM character_lifecycle WHERE uid=?',(uid,)).fetchone()

            if state and state[0]:return self._row(None)

        return value



    def artifact(self,uid):

        """Current owned identity and Artifact in one read-only SQL snapshot."""

        uid=character_uid(uid)

        from els_server.storage.read_scope import snapshot_connection

        with snapshot_connection(self.path) as db:

            db.execute('BEGIN')

            value=self._identity(db,uid)

            row=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()

            value['artifact']=dict(template=row[0],evolution=row[1],level=row[2],experience=row[3],potentials=json.loads(row[4])) if row else None

            return value



    def public_custom(self,uid):

        """Current owned identity/title/custom fields for peer restoration."""

        uid=character_uid(uid)

        from els_server.storage.character_custom import actor_snapshot as custom_snapshot

        from els_server.storage.titles import equipped

        with snapshot_connection(self.path) as db:

            db.execute('BEGIN')

            value=self._identity(db,uid)

            value['character_custom']=custom_snapshot(db,uid,self.account_id)

            value['title']=equipped(db,uid)

            return value



    def get(self,uid):

        uid=character_uid(uid)

        return next(iter(self._project(uid)),None) or self._row(None)



    def name_available(self,name):

        validate_name(name)

        with closing(sqlite3.connect(self.path,timeout=10)) as db:

            return db.execute('SELECT 1 FROM characters WHERE name_key=?',(name.casefold(),)).fetchone() is None



    def create(self,name,unit_type,operation_id,*,quick_start=False):

        validate_name(name)

        if type(unit_type) is not int or unit_type not in BASE_CLASSES:raise ValueError('Unknown character type')

        from els_server.game_data import client_data

        template=client_data().unit(BASE_CLASSES[unit_type])

        if template['unitType']!=unit_type:raise ValueError('Client character template mismatch')

        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:raise ValueError('Creation operation identity')

        if type(quick_start)is not bool:raise ValueError('Quick Start creation flag')

        digest=hashlib.sha256(json.dumps([name,unit_type]+([True]if quick_start else []),ensure_ascii=False).encode()).hexdigest()

        # Cold source imports can parse large pinned client catalogs. Complete

        # these read-only dependencies before acquiring SQLite's sole writer.

        # Ownership, capacity, UID allocation, items and wire validation below

        # still share the original atomic creation transaction.

        from els_server.storage.character_lifecycle import check_creation,current_time,created

        from els_server.storage.bag_capacity import grant_starting_fashion

        from els_server.domain.tutorial_quests import starting_town

        from els_server.storage.role_loadout import grant_loadout

        from els_server.domain.character_rules import default_slots

        from els_server.domain.skill_rules import equippable_skills

        from els_server.domain.skill_state import encode_slots

        from els_server.protocol.character_messages import create_ack

        from els_server.domain.role_progression import catalog as role_catalog

        from els_server.domain.equipment_requirements import catalog as equipment_catalog

        town=20000 if quick_start else starting_town(unit_type)

        role_catalog();equipment_catalog();prepare_character_catalogs()

        from els_server.domain.resonance_allocation_flow import definitions,profiles

        from els_server.storage.resonance_state import snapshot as resonance_snapshot

        definitions()

        with closing(sqlite3.connect(self.path,timeout=10)) as db,write_transaction(db):

            old=db.execute('SELECT request_hash,uid FROM character_creation_receipts WHERE operation_id=?',(operation_id,)).fetchone()

            if old:

                if old[0]!=digest:raise ValueError('Conflicting creation retry')

                if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(old[1],)).fetchone()!=(self.account_id,):raise ValueError('Creation receipt belongs to another account')

                uid=old[1]

            else:

                now=current_time();check_creation(db,self.account_id,now)

                if db.execute('SELECT 1 FROM characters WHERE name_key=?',(name.casefold(),)).fetchone():raise ValueError('Character name already exists')

                uid=db.execute('SELECT COALESCE(MAX(uid),1000)+1 FROM characters').fetchone()[0];character_uid(uid)

                db.execute('INSERT INTO characters VALUES (?,?,?,?,?,1,0,0,0)',(uid,name,name.casefold(),unit_type,BASE_CLASSES[unit_type]))

                db.execute('INSERT INTO character_owners VALUES (?,?)',(uid,self.account_id))

                created(db,uid,self.account_id,now)

                starting_bags=grant_starting_fashion(db,uid)

                # New identities and their role-specific starter items commit

                # together; retry receipts never grant a second set.

                db.execute('INSERT INTO location VALUES (?,?,0,0,0,0,0,0)',(uid,town))

                db.execute('INSERT INTO reward_balances VALUES (?,0,0,0)',(uid,))

                character=dict(DEFAULT_CHARACTER,uid=uid,account_id=self.account_id,name=name,unit_type=unit_type,unit_class=BASE_CLASSES[unit_type],artifact=None,bag_capacities=starting_bags)

                character['resonance']=resonance_snapshot(db,uid,self.account_id)

                from els_server.storage.achievements import statuses as achievement_statuses

                character['achievement_status']=achievement_statuses(db,self.account_id,(uid,))[uid]

                if character['resonance']['enabled']:

                    p=profiles(db);p.initialize()

                    p.accounts.migrate_dominated_legacy(account=self.account_id,character=uid)

                    p.synchronize(account=self.account_id,character=uid).notice()

                items=grant_loadout(db,character)

                # Native tutorial skill step admits A/C; sequential A/S

                # left the second starter skill blocked until the next step.

                # Only new rows change. Replays and saved player slots stay put.

                starting_slots=list(default_slots(character))

                starting_slots[3],starting_slots[1]=starting_slots[1],0

                db.execute('INSERT INTO skill_slots VALUES (?,?,0)',(uid,encode_slots(tuple(starting_slots),equippable_skills(character),character)))

                # Refuse an unencodable initial character before committing any

                # identity, equipment, sequence allocation or creation receipt.

                create_ack(character,items=items)

                if quick_start:

                    from els_server.storage.quick_start import enroll

                    enroll(db,uid,self.account_id,now)

                db.execute('INSERT INTO character_creation_receipts VALUES (?,?,?)',(operation_id,digest,uid))

        return self.get(uid)



from els_server.storage.read_scope import snapshot_connection





_PUBLIC_CUSTOM_SCHEMAS={'character_custom_permanent': 'CREATE TABLE character_custom_permanent (owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,source_template INTEGER NOT NULL,PRIMARY KEY(owner,custom_id))', 'character_custom_permanent_selection': 'CREATE TABLE character_custom_permanent_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>=0))', 'character_custom_permanent_extra_selection': 'CREATE TABLE character_custom_permanent_extra_selection(owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL,custom_id INTEGER NOT NULL CHECK(custom_id>=0),variant INTEGER NOT NULL CHECK(variant BETWEEN 1 AND 3),PRIMARY KEY(owner,slot))', 'character_custom_permanent_selection_slots': 'CREATE TABLE character_custom_permanent_selection_slots (owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL CHECK(slot IN (7,8,13,14,24,25,26,27)),custom_id INTEGER NOT NULL CHECK(custom_id>=0),PRIMARY KEY(owner,slot))', 'character_custom_permanent_face_selection': 'CREATE TABLE character_custom_permanent_face_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>0))', 'character_custom_permanent_abilities': 'CREATE TABLE character_custom_permanent_abilities(owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,ability INTEGER NOT NULL CHECK(ability>0),PRIMARY KEY(owner,custom_id))', 'title_ownership': "CREATE TABLE title_ownership (scope TEXT NOT NULL CHECK(scope IN ('account','character')), subject INTEGER NOT NULL, title INTEGER NOT NULL, acquired_by TEXT NOT NULL, acquired_at INTEGER NOT NULL, expires_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scope,subject,title))", 'title_equipment': 'CREATE TABLE title_equipment (owner INTEGER PRIMARY KEY REFERENCES characters(uid), title INTEGER NOT NULL)', 'completed_quests': 'CREATE TABLE completed_quests (owner INTEGER NOT NULL REFERENCES characters(uid), quest INTEGER NOT NULL, completed_at INTEGER NOT NULL, reward_json TEXT NOT NULL, PRIMARY KEY(owner,quest))'}





def _public_identity_rows(db,entries,lifecycle):
    prefix='WITH requested(i,uid,account)AS(VALUES '+','.join('(?,?,?)'for _ in entries)+') '
    arguments=tuple(value for index,repo,uid in entries for value in(index,uid,repo.account_id))
    life='l.finalized_at'if lifecycle else'0'
    join=' LEFT JOIN character_lifecycle l ON l.uid=c.uid'if lifecycle else''
    sql=prefix+'SELECT r.i,c.uid,c.name,c.unit_type,c.unit_class,c.level,c.transcendence,c.master,c.revision,'+life+' FROM requested r LEFT JOIN character_owners o ON o.uid=r.uid AND o.account_id=r.account LEFT JOIN characters c ON c.uid=o.uid'+join+' ORDER BY r.i'
    rows={row[0]:row[1:]for row in db.execute(sql,arguments)};values={}
    for index,repo,uid in entries:
        row=rows[index];value=repo._row(row[:8]if row[0]is not None else None)
        value['account_id']=repo.account_id
        if row[8]:repo._row(None)
        values[index]=value
    return values


def public_identity_views(requests,*,luciel=False):

    """Read nearby owned identities together in one current SQL snapshot."""

    from collections import defaultdict

    from els_server.storage.initialization_checks import CHARACTERS

    requests=tuple((repo,character_uid(uid))for repo,uid in requests)

    result=[None]*len(requests);groups=defaultdict(list)

    for index,(repo,uid)in enumerate(requests):groups[Path(repo.path)].append((index,repo,uid))

    for path,entries in groups.items():

        ordinary=all(type(repo)is Characters and getattr(repo.identity,'__func__',None)is Characters.identity

            and getattr(repo._identity,'__func__',None)is Characters._identity and repo._row is Characters._row for _,repo,_ in entries)

        values=None

        if ordinary:

            with snapshot_connection(path)as db:

                db.execute('BEGIN')

                schema=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'AND name IN('characters','character_owners','character_lifecycle')"))

                lifecycle=schema.get('character_lifecycle')

                standard=(all(schema.get(name)==CHARACTERS[name]for name in('characters','character_owners'))

                    and db.execute('PRAGMA temp.schema_version').fetchone()==(0,)

                    and(lifecycle is None or lifecycle==_PUBLIC_IDENTITY_LIFECYCLE_SCHEMA))

                if standard:

                    values=_public_identity_rows(db,entries,lifecycle)
                    if luciel:
                        from els_server.storage.luciel_state import state,active_state
                        for index,repo,uid in entries:
                            value=values[index]
                            if value['unit_type']==10:
                                value['luciel_style']=state(db,uid)['style']
                                value['luciel_active_unit']=active_state(db,uid)['active_unit']
        if values is None:

            values={index:repo.identity(uid)for index,repo,uid in entries}

            if luciel:

                for index,repo,uid in entries:

                    if values[index]['unit_type']==10:values[index]=repo.get(uid)

        for index,value in values.items():result[index]=value

    return result





_PUBLIC_IDENTITY_LIFECYCLE_SCHEMA='CREATE TABLE character_lifecycle (uid INTEGER PRIMARY KEY REFERENCES characters(uid), account_id INTEGER NOT NULL, created_at INTEGER NOT NULL CHECK(created_at>=0), requested_at INTEGER NOT NULL DEFAULT 0, finalize_at INTEGER NOT NULL DEFAULT 0, restore_at INTEGER NOT NULL DEFAULT 0, cooldown_until INTEGER NOT NULL DEFAULT 0, finalized_at INTEGER NOT NULL DEFAULT 0)'





def public_custom_views(requests):

    """Fresh readonly peer views; each original owner/lifecycle guard still runs.



    Current schemas fetch shared custom/title rows once per exact save path.

    These rows and results never survive this operation or authorize writes.

    Scalar/overridden readers and other saved schemas keep their old consumer.

    """

    from collections import defaultdict

    requests=tuple((repo,character_uid(uid))for repo,uid in requests)

    groups=defaultdict(list);result=[None]*len(requests)

    for index,(repo,uid)in enumerate(requests):groups[Path(repo.path)].append((index,repo,uid))

    for path,entries in groups.items():

        ordinary=all(type(repo)is Characters and getattr(repo.public_custom,'__func__',None)is Characters.public_custom

            and getattr(repo._identity,'__func__',None)is Characters._identity and repo._row is Characters._row for _,repo,_ in entries)

        views=_public_custom_group(path,entries)if ordinary else None

        if views is None:views={index:repo.public_custom(uid)for index,repo,uid in entries}

        for index,value in views.items():result[index]=value

    return result





def _public_custom_group(path,entries):

    import time

    from collections import defaultdict

    from els_server.storage import character_custom as custom,titles,custom_periods

    from els_server.storage.initialization_checks import CHARACTERS

    expected={**_PUBLIC_CUSTOM_SCHEMAS,'character_lifecycle':_PUBLIC_IDENTITY_LIFECYCLE_SCHEMA,**{name:CHARACTERS[name]for name in('characters','character_owners')}}

    with snapshot_connection(path)as db:

        db.execute('BEGIN')

        schema=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'AND name IN("+','.join('?'for _ in expected)+')',tuple(expected)))

        if (any(schema.get(name)!=expected[name]for name in('characters','character_owners'))

                or any(expected[name]!=sql for name,sql in schema.items())

                or db.execute('PRAGMA temp.schema_version').fetchone()!=(0,)):return None

        # Never cache authorization. Each role is checked on this fresh SQL

        # snapshot through its original account and finalized-state consumer.

        values=_public_identity_rows(db,entries,schema.get('character_lifecycle'))

        prefix='WITH requested(i,uid,account)AS(VALUES '+','.join('(?,?,?)'for _ in entries)+') '

        arguments=tuple(value for index,repo,uid in entries for value in(index,uid,repo.account_id))

        def fetch(table,columns,*,join='t.owner=r.uid',order=''):

            rows=defaultdict(list)

            if table in schema:

                sql=prefix+'SELECT r.i,'+columns+' FROM requested r JOIN '+table+' t ON '+join+' ORDER BY r.i'+(','+order if order else'')

                for row in db.execute(sql,arguments):rows[row[0]].append(row[1:])

            return rows

        permanent=fetch(custom.OWNED,'t.custom_id,t.source_template',order='t.custom_id')

        abilities=fetch('character_custom_permanent_abilities','t.custom_id,t.ability',order='t.custom_id')

        main=fetch(custom.SELECTED,'t.custom_id')

        side=fetch(custom.SIDE_SELECTED,'t.slot,t.custom_id',order='t.slot')

        face=fetch(custom.FACE_SELECTED,'t.custom_id')

        extra=fetch(custom.EXTRA_SELECTED,'t.slot,t.custom_id,t.variant',order='t.slot')

        completed=fetch('completed_quests','t.quest',order='t.quest')

        ownership=fetch('title_ownership','t.title,t.acquired_by,t.expires_at,t.scope,t.subject',

            join="(t.scope='character'AND t.subject=r.uid)OR(t.scope='account'AND t.subject=r.account)",order='t.title')

        equipment=fetch('title_equipment','t.title')

        periods=defaultdict(list)
        if custom_periods.exists(db):
            for row in db.execute(prefix+'SELECT r.i,t.custom_id,t.source_template,t.starts_at,t.expires_at FROM requested r JOIN character_custom_periods t ON t.owner=r.uid ORDER BY r.i,t.custom_id',arguments):periods[row[0]].append(row[1:])
        now=int(time.time())
        for index,repo,uid in entries:

            value=values[index]

            role=tuple(value[name]for name in('unit_type','unit_class','level'))

            value['character_custom']=custom._project_rows(role,permanent[index],abilities[index],main[index],side[index],face[index],extra[index],periods=custom_periods.owned_rows(periods[index],now))

            title_character={name:value[name]for name in('uid','name','unit_type','unit_class','level','account_id')}

            title_character['title_completed_quests']=tuple(row[0]for row in completed[index])

            owned=titles._owned_rows(title_character,now,ownership[index])

            value['title']=titles._equipped_rows(title_character,owned,next(iter(equipment[index]),None))

        return values

