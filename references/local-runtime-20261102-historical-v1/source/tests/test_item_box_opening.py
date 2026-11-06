"""Official Raid reward boxes reach their native preview/open handlers from the session."""
import asyncio,sqlite3,struct,time,unittest
from contextlib import closing
from tests import test_npc_sale as fixture
from els_server.domain.raid_reward_items import boxes
from els_server.domain.cubes import catalog
from els_server.protocol.protocol_codec import Event


RAID_BOX = 136051
ENTRIES = (136042,136045,136048)
ARTIFACT_BOX = 723618
ARTIFACT_PIECES = (168600,168601,168602,168603)
ABYSS_BOX = 723621
ABYSS_PIECES = (30675,30676,30677)
FORCE_E_BOX = 723687
FORCE_A_BOX = 723688
FORCE_E_ENTRIES = 120
FORCE_A_ENTRIES = 240
FORCE_E_CHOICE = 390188
REFUSED = (135869,)
# Official fixed boxes: 118655 is the per-character white-realm mech armour
# reward of the epic quest "进入瑟芬提姆"; 117542 is Ariel's 20-Essence bag.
ARMOUR_BOX = 118655
ESSENCE_BAG = 117542
ESSENCE = 78931
ARMOUR_FAMILY1 = (118381,118382,118383,118384)
ARMOUR_FAMILY10 = (118417,118418,118419,118420)
ARMOUR_FAMILY10_MINOR = (118437,118438,118439,118440)
# Official promotion-outfit boxes: the client ships no ItemGroup table, so the
# granted set is the job ancestor's units promotion* outfit. Family 1 route 1
# stage 1/2/3 stand in for the three advancement stages.
PROMOTION_STAGE1 = 10
PROMOTION_STAGE2 = 100
PROMOTION_STAGE3 = 150
PROMOTION_BOX_109999 = 109999
PROMOTION_BOX_110850 = 110850
PROMOTION_BOX_135666 = 135666
PROMOTION_BOX_135867 = 135867
PROMOTION_BOX_135871 = 135871
OUTFIT_STAGE1 = (130370,128037,128038,128039,128040)
OUTFIT_STAGE2 = (131136,131137,131138,131139,131140)
OUTFIT_STAGE3 = (42297,42298,42299,42300,42301,42303)
DAY = 86400
# Pinned before any save opens: enabling the 2026 owned-growth bundles registers
# five additional boxes on top of this shipped cube table.
CATALOG = catalog()


def preview(template,keys=(),flag1=0,flag2=0):
    # 2353800: template, vector<int>, two mode bytes.
    return struct.pack('>iI',template,len(keys))+b''.join(struct.pack('>i',k) for k in keys)+bytes((flag1,flag2))


def use(uid,choices=(),option=0):
    # 2353C10 / DB1A20: UID, 3 bytes, ordered set<int>, i32 option.
    return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',i) for i in choices)+struct.pack('>i',option)


class ItemBoxOpeningTests(fixture.SaleTests):
    def grant_box(self,count=1,template=RAID_BOX,slot=0):
        # 136051 is an owned-only Raid drop: no acquisition policy admits a new
        # grant, so the fixture writes the exact instance the phase writer would.
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        from els_server.storage.item_instances import insert,next_uid
        item=dict(uid=None,template=template,metadata=VERIFIED_TEMPLATES[template],
                  count=count,group=TEMPLATE_BAG_GROUPS[template],slot=slot)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            item['uid']=next_uid(db);insert(db,1001,item)
        return item

    def session(self):
        from els_server.application import Application
        from els_server.config import ServerConfig
        app=Application(ServerConfig(state_file=self.path,log_dir=self.path.parent/'logs'))
        self.addCleanup(app.executor.shutdown,wait=True)
        app.account=self.account.root
        s=asyncio.run(app.session())
        s.role='game';s.phase='town_ready';s.completed.update((0x28,0x225,0x227))
        return s

    def preview_ack(self,events):
        return next(e for e in events if e.kind==0x55a)

    def set_class(self,unit_class):
        # The promotion boxes resolve by the saved character's job stage.
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE characters SET unit_class=? WHERE uid=1001',(unit_class,))

    def set_character(self,unit_class,unit_type,active=None):
        # The armour box resolves by the saved character's family, and Lu/Ciel
        # additionally by the currently selected unit.
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE characters SET unit_class=?,unit_type=? WHERE uid=1001',(unit_class,unit_type))
            if active is not None:
                from els_server.storage.luciel_state import ensure_active
                ensure_active(db)
                db.execute('INSERT OR REPLACE INTO luciel_active_states(uid,active_unit,revision) VALUES(1001,?,0)',(active,))

    def entries_of(self,reply):
        count=struct.unpack_from('>I',reply.payload,17)[0]
        return tuple(struct.unpack_from('>iii',reply.payload,21+12*i)[0] for i in range(count))

    def granted(self,templates):
        return [sum(i['count'] for i in self.items() if i['template']==t) for t in templates]

    def open_ok(self,s,item,sequence=1):
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),sequence)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],0)
        return events

    def test_raid_box_catalog_has_no_overlap_with_fixed_cubes(self):
        self.assertEqual(len(boxes()),30)
        self.assertEqual(len(CATALOG),81)
        self.assertEqual(set(int(k) for k in boxes())&set(CATALOG),set())
        self.assertEqual(set(int(k) for k in boxes())&set(catalog()),set())

    def test_preview_136051_returns_three_official_entries(self):
        self.grant_box(); s=self.session()
        event=Event(0x202,kind=0x559,payload=preview(RAID_BOX))
        self.assertEqual((event.uid,event.target_uid,event.payload_mode),(2**64-1,2**64-1,0))
        self.assertEqual(event.performers,())
        reply=self.preview_ack(s.handle(event,1))
        self.assertEqual(reply.kind,0x55a)
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,RAID_BOX))
        self.assertEqual(struct.unpack_from('>B',reply.payload,12)[0],0)
        self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],0)
        self.assertEqual(struct.unpack_from('>I',reply.payload,17)[0],3)
        rows=[struct.unpack_from('>iii',reply.payload,21+12*i) for i in range(3)]
        self.assertEqual(tuple(r[0] for r in rows),ENTRIES)
        self.assertEqual([r[1] for r in rows],[1,1,1])

    def test_open_136051_consumes_one_box_and_grants_one_entry(self):
        item=self.grant_box(2); s=self.session()
        acknowledged=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(RAID_BOX)),1))
        self.assertEqual(struct.unpack_from('>i',acknowledged.payload)[0],0)
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),2)
        ack=next(e for e in events if e.kind==0x197)
        self.assertEqual(struct.unpack_from('>i',ack.payload)[0],0)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(sum(i['count'] for i in self.items() if i['template'] in ENTRIES),1)

    def test_open_136051_replay_is_idempotent(self):
        item=self.grant_box(); s=self.session()
        s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(sum(i['count'] for i in self.items() if i['template'] in ENTRIES),1)
        before=self.dump()
        retry=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in retry if e.kind==0x197).payload)[0],0)
        self.assertEqual(sum(i['count'] for i in self.items() if i['template'] in ENTRIES),1)
        self.assertEqual(self.dump(),before)

    def test_preview_723618_returns_four_artifact_pieces(self):
        self.grant_box(template=ARTIFACT_BOX); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(ARTIFACT_BOX)),1))
        self.assertEqual(reply.kind,0x55a)
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,ARTIFACT_BOX))
        self.assertEqual(struct.unpack_from('>B',reply.payload,12)[0],0)
        self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],0)
        self.assertEqual(struct.unpack_from('>I',reply.payload,17)[0],4)
        rows=[struct.unpack_from('>iii',reply.payload,21+12*i) for i in range(4)]
        self.assertEqual(tuple(r[0] for r in rows),ARTIFACT_PIECES)
        self.assertEqual([r[2] for r in rows],[1,1,1,2])

    def test_open_723618_grants_all_four_pieces(self):
        item=self.grant_box(2,template=ARTIFACT_BOX); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        ack=next(e for e in events if e.kind==0x197)
        self.assertEqual(struct.unpack_from('>i',ack.payload)[0],0)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual([sum(i['count'] for i in self.items() if i['template']==t) for t in ARTIFACT_PIECES],[1,1,1,2])
        retry=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in retry if e.kind==0x197).payload)[0],0)
        self.assertEqual([sum(i['count'] for i in self.items() if i['template']==t) for t in ARTIFACT_PIECES],[1,1,1,2])

    def test_preview_723621_returns_three_accessories(self):
        self.grant_box(template=ABYSS_BOX); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(ABYSS_BOX)),1))
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,ABYSS_BOX))
        self.assertEqual(struct.unpack_from('>I',reply.payload,17)[0],3)
        rows=[struct.unpack_from('>iii',reply.payload,21+12*i) for i in range(3)]
        self.assertEqual(tuple(r[0] for r in rows),ABYSS_PIECES)
        self.assertEqual([r[2] for r in rows],[1,1,1])

    def test_open_723621_grants_all_three_accessories(self):
        item=self.grant_box(2,template=ABYSS_BOX); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],0)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual([sum(i['count'] for i in self.items() if i['template']==t) for t in ABYSS_PIECES],[1,1,1])
        retry=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in retry if e.kind==0x197).payload)[0],0)
        self.assertEqual([sum(i['count'] for i in self.items() if i['template']==t) for t in ABYSS_PIECES],[1,1,1])

    def test_preview_change_force_boxes_returns_official_entry_counts(self):
        self.grant_box(template=FORCE_E_BOX); self.grant_box(template=FORCE_A_BOX,slot=1); s=self.session()
        for template,count in ((FORCE_E_BOX,FORCE_E_ENTRIES),(FORCE_A_BOX,FORCE_A_ENTRIES)):
            reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(template)),1))
            self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,template))
            self.assertEqual(struct.unpack_from('>I',reply.payload,17)[0],count)
            self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],1)

    def test_open_change_force_box_grants_only_the_selected_item(self):
        item=self.grant_box(2,template=FORCE_E_BOX); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'],choices=(FORCE_E_CHOICE,))),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],0)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==FORCE_E_CHOICE),1)

    def test_open_change_force_box_rejects_choice_outside_announcement(self):
        item=self.grant_box(template=FORCE_E_BOX); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'],choices=(720748,))),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],-1)
        self.assertEqual(sum(i['count'] for i in self.items() if i['uid']==item['uid']),1)

    def test_preview_109999_returns_stage_one_outfit_entries(self):
        self.grant_box(template=PROMOTION_BOX_109999); self.set_class(PROMOTION_STAGE3); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(PROMOTION_BOX_109999)),1))
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,PROMOTION_BOX_109999))
        self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],0)
        self.assertEqual(self.entries_of(reply),OUTFIT_STAGE1)

    def test_open_109999_grants_stage_one_outfit_with_fifteen_day_expiry(self):
        item=self.grant_box(template=PROMOTION_BOX_109999); self.set_class(PROMOTION_STAGE3); s=self.session()
        started=int(time.time()); self.open_ok(s,item); finished=int(time.time())
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted(OUTFIT_STAGE1),[1]*5)
        deadlines=[next(i['expires_at'] for i in self.items() if i['template']==t) for t in OUTFIT_STAGE1]
        self.assertTrue(all(started+15*DAY<=d<=finished+15*DAY for d in deadlines))

    def test_open_135871_grants_stage_one_outfit_with_three_day_expiry(self):
        item=self.grant_box(template=PROMOTION_BOX_135871); self.set_class(PROMOTION_STAGE2); s=self.session()
        started=int(time.time()); self.open_ok(s,item); finished=int(time.time())
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted(OUTFIT_STAGE1),[1]*5)
        deadlines=[next(i['expires_at'] for i in self.items() if i['template']==t) for t in OUTFIT_STAGE1]
        self.assertTrue(all(started+3*DAY<=d<=finished+3*DAY for d in deadlines))

    def test_open_135666_grants_current_stage_outfit_with_seven_day_expiry(self):
        item=self.grant_box(count=2,template=PROMOTION_BOX_135666); self.set_class(PROMOTION_STAGE3); s=self.session()
        started=int(time.time()); self.open_ok(s,item); finished=int(time.time())
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(self.granted(OUTFIT_STAGE3),[1]*6)
        deadlines=[next(i['expires_at'] for i in self.items() if i['template']==t) for t in OUTFIT_STAGE3]
        self.assertTrue(all(started+7*DAY<=d<=finished+7*DAY for d in deadlines))

    def test_open_110850_requires_second_advancement(self):
        item=self.grant_box(template=PROMOTION_BOX_110850); self.set_class(PROMOTION_STAGE1); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],-1)
        self.assertEqual(sum(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(self.granted(OUTFIT_STAGE1),[0]*5)

    def test_preview_135867_returns_stage_three_outfit_entries(self):
        self.grant_box(template=PROMOTION_BOX_135867); self.set_class(PROMOTION_STAGE3); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(PROMOTION_BOX_135867)),1))
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,PROMOTION_BOX_135867))
        self.assertEqual(struct.unpack_from('>i',reply.payload,13)[0],0)
        self.assertEqual(self.entries_of(reply),OUTFIT_STAGE3)

    def test_open_135867_grants_stage_three_outfit_with_fifteen_day_expiry(self):
        item=self.grant_box(template=PROMOTION_BOX_135867); self.set_class(PROMOTION_STAGE3); s=self.session()
        started=int(time.time()); self.open_ok(s,item); finished=int(time.time())
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted(OUTFIT_STAGE3),[1]*6)
        deadlines=[next(i['expires_at'] for i in self.items() if i['template']==t) for t in OUTFIT_STAGE3]
        self.assertTrue(all(started+15*DAY<=d<=finished+15*DAY for d in deadlines))

    def test_open_135867_requires_third_advancement(self):
        item=self.grant_box(template=PROMOTION_BOX_135867); self.set_class(PROMOTION_STAGE2); s=self.session()
        events=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in events if e.kind==0x197).payload)[0],-1)
        self.assertEqual(sum(i['count'] for i in self.items() if i['uid']==item['uid']),1)
        self.assertEqual(self.granted(OUTFIT_STAGE3),[0]*6)

    def test_open_promotion_box_replay_is_idempotent(self):
        item=self.grant_box(template=PROMOTION_BOX_109999); self.set_class(PROMOTION_STAGE3); s=self.session()
        self.open_ok(s,item)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted(OUTFIT_STAGE1),[1]*5)
        before=self.dump()
        retry=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in retry if e.kind==0x197).payload)[0],0)
        self.assertEqual(self.granted(OUTFIT_STAGE1),[1]*5)
        self.assertEqual(self.dump(),before)

    def test_preview_118655_returns_the_character_family_armour_set(self):
        self.set_character(10,1); self.grant_box(template=ARMOUR_BOX); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(ARMOUR_BOX)),1))
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,ARMOUR_BOX))
        self.assertEqual(self.entries_of(reply),ARMOUR_FAMILY1)
        rows=[struct.unpack_from('>iii',reply.payload,21+12*i) for i in range(4)]
        self.assertEqual([r[1] for r in rows],[1,1,1,1])

    def test_open_118655_grants_the_family_armour_set_permanently(self):
        self.set_character(10,1); item=self.grant_box(template=ARMOUR_BOX); s=self.session()
        self.open_ok(s,item)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted(ARMOUR_FAMILY1),[1]*4)
        self.assertEqual([i.get('expires_at')for i in self.items()if i['template']in ARMOUR_FAMILY1],[None]*4)

    def test_open_118655_uses_the_selected_luciel_armour_set(self):
        self.set_character(177,10,1); item=self.grant_box(template=ARMOUR_BOX); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(ARMOUR_BOX)),1))
        self.assertEqual(self.entries_of(reply),ARMOUR_FAMILY10_MINOR)
        self.open_ok(s,item,sequence=2)
        self.assertEqual(self.granted(ARMOUR_FAMILY10_MINOR),[1]*4)
        self.assertEqual(self.granted(ARMOUR_FAMILY10),[0]*4)

    def test_preview_117542_returns_twenty_essences(self):
        self.grant_box(template=ESSENCE_BAG); s=self.session()
        reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(ESSENCE_BAG)),1))
        self.assertEqual(struct.unpack_from('>ii',reply.payload),(0,ESSENCE_BAG))
        self.assertEqual(self.entries_of(reply),(ESSENCE,))
        self.assertEqual(struct.unpack_from('>i',reply.payload,25)[0],20)

    def test_open_117542_grants_twenty_essences_and_replays_idempotently(self):
        item=self.grant_box(template=ESSENCE_BAG); s=self.session()
        self.open_ok(s,item)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(self.granted((ESSENCE,)),[20])
        before=self.dump()
        retry=s.handle(Event(0x202,kind=0x196,payload=use(item['uid'])),1)
        self.assertEqual(struct.unpack_from('>i',next(e for e in retry if e.kind==0x197).payload)[0],0)
        self.assertEqual(self.granted((ESSENCE,)),[20])
        self.assertEqual(self.dump(),before)

    def test_unregistered_boxes_stay_refused(self):
        self.grant_box(); s=self.session()
        for template in REFUSED:
            reply=self.preview_ack(s.handle(Event(0x202,kind=0x559,payload=preview(template)),1))
            self.assertEqual(reply.kind,0x55a)
            self.assertEqual(struct.unpack_from('>ii',reply.payload),(-1,template))

    def test_raid_box_requires_town_ready_game_and_native_envelope(self):
        self.grant_box(); s=self.session()
        for change in ('phase','role','uid'):
            before=self.dump()
            event=Event(0x202,kind=0x559,payload=preview(RAID_BOX))
            if change=='phase':s.phase='channels_ready'
            elif change=='role':s.role='lobby'
            else:event=Event(0x202,kind=0x559,uid=7,payload=preview(RAID_BOX))
            reply=self.preview_ack(s.handle(event,1))
            self.assertEqual(struct.unpack_from('>ii',reply.payload),(-1,RAID_BOX))
            self.assertEqual(self.dump(),before)
            s.phase='town_ready';s.role='game'


def load_tests(loader,tests,pattern):
    # The shared sale fixture carries unrelated marketplace cases; this module
    # only claims its own native box-opening coverage.
    return unittest.TestSuite(ItemBoxOpeningTests(name) for name in (
        'test_raid_box_catalog_has_no_overlap_with_fixed_cubes',
        'test_preview_136051_returns_three_official_entries',
        'test_open_136051_consumes_one_box_and_grants_one_entry',
        'test_open_136051_replay_is_idempotent',
        'test_preview_723618_returns_four_artifact_pieces',
        'test_open_723618_grants_all_four_pieces',
        'test_preview_723621_returns_three_accessories',
        'test_open_723621_grants_all_three_accessories',
        'test_preview_change_force_boxes_returns_official_entry_counts',
        'test_open_change_force_box_grants_only_the_selected_item',
        'test_open_change_force_box_rejects_choice_outside_announcement',
        'test_preview_109999_returns_stage_one_outfit_entries',
        'test_open_109999_grants_stage_one_outfit_with_fifteen_day_expiry',
        'test_open_135871_grants_stage_one_outfit_with_three_day_expiry',
        'test_open_135666_grants_current_stage_outfit_with_seven_day_expiry',
        'test_open_110850_requires_second_advancement',
        'test_preview_135867_returns_stage_three_outfit_entries',
        'test_open_135867_grants_stage_three_outfit_with_fifteen_day_expiry',
        'test_open_135867_requires_third_advancement',
        'test_open_promotion_box_replay_is_idempotent',
        'test_preview_118655_returns_the_character_family_armour_set',
        'test_open_118655_grants_the_family_armour_set_permanently',
        'test_open_118655_uses_the_selected_luciel_armour_set',
        'test_preview_117542_returns_twenty_essences',
        'test_open_117542_grants_twenty_essences_and_replays_idempotently',
        'test_unregistered_boxes_stay_refused',
        'test_raid_box_requires_town_ready_game_and_native_envelope'))
