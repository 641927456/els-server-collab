"""Owned source-delivery boundaries; full native/runtime QA is separate."""
import importlib.util
from pathlib import Path
import hashlib,json,struct,sys,unittest
from els_server.protocol.protocol_codec import Event

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'references/native-server-attributes-20261027-v1/els_server/domain/native_skill_delivery_sources.py'
SPEC=importlib.util.spec_from_file_location('candidate_skill_delivery_sources',PATH)
M=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=M;SPEC.loader.exec_module(M)
U32=lambda n:struct.pack('>I',n)


def records(values):
    return U32(len(values))+b''.join(struct.pack('>iBiB',sid,rank,0,0)for sid,rank in values)


def identifiers(values):return U32(len(values))+b''.join(struct.pack('>i',s)for s in values)


def preset(*,forces=None,slots=None,traits=()):
    raw=records(slots or((0,0),)*22)+U32(len(traits))+b''.join(struct.pack('>ii',*v)for v in traits)
    if forces is None:return raw+bytes(8)
    return raw+U32(3)+b''.join(struct.pack('>iBB',s,r,0)for s,r in forces[:3])+U32(8)+b''.join(struct.pack('>iBB',s,r,0)for s,r in forces[3:])


def initial(*,uid=1001,learned=((25410,4),(25030,1)),ids=(),pages=None,selected=1,forces=None):
    pages=pages or(preset(forces=forces),)
    raw=struct.pack('>QI',uid,len(pages))+b''.join(bytes([i])+p for i,p in enumerate(pages))
    return Event(0x201,kind=0x55b,payload=raw+records(learned)+bytes(17)+bytes([selected,len(pages)])+identifiers(ids))


def notice(kind,raw):return Event(0x201,kind=kind,payload=raw)


def copy_event(*,forces=None,uid=1001,kind=0xd9):
    # Explicit small Unit-field binding control, not a native full Unit fixture.
    field=records(((0,0),)*22)+bytes(4)+records(((25410,4),))+bytes(8)+b'\1\1'+preset(forces=forces)+records(((25410,4),))+b'\0'
    fields=(('prefix',bytes(9)+struct.pack('>Q',uid)),('0x14e',field))
    raw=b''.join(v for k,v in fields)
    event=notice(kind,(bytes(4)if kind==0x2a else b'')+raw+b'other-current-copy-tail')
    return event,fields


class SkillDeliverySourcesTests(unittest.TestCase):
    def written(self,state,event,*,ready=True):return state.written(event,ordinary_page_ready=ready)

    def test_whole_original131_legal_rank_restore_repeat_keeps_extra_channel(self):
        proof=json.loads((PATH.parents[2]/'native-whole131-source-goldens-v5.json').read_bytes())
        self.assertTrue(proof['ok']);self.assertEqual(proof['cases'],3)
        self.assertEqual(proof['qualified_context']['original_ordinary_calculation_constructor'],'98F400')
        first=proof['rows'][0]
        state=M.SkillSources(1007,learned=tuple(map(tuple,proof['rows'][-1]['queries'])),
                            unsealed=(),extra=tuple(map(tuple,first['boundaries_before']['extra'])))
        for row in proof['rows']:
            before=row['boundaries_before'];after=row['boundaries_after']
            self.assertEqual(state.extra,tuple(map(tuple,before['extra'])))
            raw=bytes.fromhex(row['payload_hex'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['payload_sha256'])
            state=self.written(state,notice(0x131,raw))
            self.assertEqual(state.learned,tuple(map(tuple,row['queries'])))
            self.assertEqual(state.extra,tuple(map(tuple,after['extra'])))
            self.assertEqual(len(state.learned),37)
            self.assertEqual((before['slot_protected_float'],after['slot_protected_float']),(12.5,12.5))
            self.assertEqual((before['preset_vector_count'],after['preset_vector_count']),(0,0))
            self.assertTrue(row['whole_original_handler_returned'])

    def test_55B_cannot_attest_Force_delivery_and_123_does_not_require_full_resend(self):
        forces=((100100,5),)+((0,0),)*10
        state=M.SkillSources(1001).constructed()
        state=self.written(state,initial(forces=forces))
        self.assertFalse(state.matches(initial(forces=forces)))
        self.assertEqual(state.forces,M.ZERO_FORCE)
        state=self.written(state,notice(0x6d1,bytes(4)+preset(forces=forces)))
        self.assertTrue(state.matches(initial(forces=forces)))
        slots=((25030,1),)+((0,0),)*21
        moved=initial(forces=forces,pages=(preset(forces=forces,slots=slots),))
        self.assertNotEqual(initial(forces=forces).payload,moved.payload)
        self.assertIs(self.written(state,notice(0x123,struct.pack('>5i',0,0,25030,-1,0))),state)
        self.assertTrue(state.matches(moved))

    def test_131_updates_existing_rank_adds_new_ID_and_preserves_other_sources(self):
        state=self.written(M.SkillSources(1001).constructed(),initial(ids=(10,)))
        event=notice(0x131,bytes(4)+records(((25410,5),(25411,4)))+identifiers((11,)))
        updated=self.written(state,event)
        self.assertEqual(updated.learned,((25030,1),(25410,5),(25411,4)))
        self.assertEqual(updated.unsealed,(10,11))
        self.assertEqual(updated.forces,state.forces)
        self.assertTrue(updated.matches(initial(learned=updated.learned,ids=(10,11))))
        unknown=self.written(M.SkillSources(1001),event)
        self.assertIsNone(unknown.learned);self.assertIsNone(unknown.unsealed)
        self.assertFalse(unknown.matches(initial(learned=updated.learned,ids=(10,11))))

    def test_explicit_zero_Force_entries_clear_and_empty_vectors_retain(self):
        forces=((100100,5),)+((0,0),)*10
        state=self.written(M.SkillSources(1001).constructed(),initial())
        state=self.written(state,notice(0x6d1,bytes(4)+preset(forces=forces)))
        self.assertIs(self.written(state,notice(0x6d1,bytes(4)+preset())),state)
        zero=self.written(state,notice(0x6d1,bytes(4)+preset(forces=M.ZERO_FORCE)))
        self.assertEqual(zero.forces,M.ZERO_FORCE)
        self.assertTrue(zero.matches(initial()))

    def test_dormant_pages_do_not_attest_selected_native_Force_application(self):
        forces=((100100,5),)+((0,0),)*10
        event=initial(pages=(preset(),preset(forces=forces),preset(forces=M.ZERO_FORCE)),selected=2)
        parsed=M.initialization(event.payload)
        self.assertEqual((parsed.selected,parsed.page_count),(2,3))
        self.assertEqual(parsed.preset.forces,forces)
        state=self.written(M.SkillSources(1001).constructed(),event)
        self.assertFalse(state.matches(event))
        p=preset(forces=forces,traits=((25030,1),))
        fixed=p[:224]+bytes(4)+p[224:]
        selected=notice(0x484,struct.pack('>4i',0,2,0,0)+fixed+p)
        state=self.written(state,selected)
        self.assertTrue(state.matches(event))
        self.assertEqual(state.learned,parsed.learned)
        self.assertIsNone(self.written(state,selected,ready=False).forces)
        inconsistent=notice(0x484,struct.pack('>4i',0,2,0,0)+fixed+preset(forces=M.ZERO_FORCE))
        with self.assertRaises(ValueError):self.written(state,inconsistent)

    def test_owned_full_copy_requires_exact_Event_and_complete_prefix_binding(self):
        forces=((100100,5),)+((0,0),)*10
        state=self.written(M.SkillSources(1001).constructed(),initial())
        for kind in(0x2a,0xd9):
            event,fields=copy_event(forces=forces,kind=kind)
            proof=M.bind_copy(event,fields);updated=state.copied(proof,event)
            self.assertEqual(updated.forces,forces)
            self.assertEqual(updated.learned,state.learned)
            self.assertTrue(updated.matches(initial(forces=forces)))
            with self.assertRaises(ValueError):state.copied(proof,notice(kind,event.payload))
            foreign,foreign_fields=copy_event(forces=forces,uid=1002,kind=kind)
            with self.assertRaises(ValueError):state.copied(M.bind_copy(foreign,foreign_fields),foreign)
            prefixed=notice(kind,b'unrelated-prefix'+event.payload)
            with self.assertRaises(ValueError):M.bind_copy(prefixed,fields)
            changed=tuple((k,v+b'\0')if k=='0x14e'else(k,v)for k,v in fields)
            with self.assertRaises(ValueError):M.bind_copy(event,changed)
        empty,fields=copy_event()
        copied=state.copied(M.bind_copy(empty,fields),empty)
        self.assertEqual(copied.forces,state.forces)
        self.assertEqual(copied.extra,((25410,4),))
        unknown=M.SkillSources(1001)
        self.assertIsNone(unknown.copied(M.bind_copy(empty,fields),empty).forces)

    def test_copied_extra_is_separate_from_ordinary_55B(self):
        state=M.SkillSources(1001).constructed()
        event,fields=copy_event()
        state=state.copied(M.bind_copy(event,fields),event)
        self.assertTrue(state.matches_extra(((25410,4),)))
        updated=self.written(state,initial(learned=((25030,1),)))
        self.assertEqual(updated.learned,((25030,1),))
        self.assertTrue(updated.matches_extra(((25410,4),)))
        self.assertFalse(updated.matches_extra(()))
        self.assertFalse(M.SkillSources(1001).matches_extra(()))
        self.assertTrue(M.SkillSources(1001).constructed().matches_extra(()))

    def test_Force_owned_increment_and_receipted_extraction_keep_other_grades(self):
        state=M.SkillSources(1001).constructed()
        for rank in(3,6,3):
            event=notice(0x6cb,struct.pack('>iiBiB',0,900405,rank,0,1))
            state=state.written(event,ordinary_page_ready=True)
        self.assertEqual(state.extra,((900405,3),(900405,6)))
        event=notice(0x6cf,struct.pack('>iiBI',0,900405,3,0))
        receipt=M.UpdateReceipt(object(),event,1001,(900405,3))
        updated=state.written(event,ordinary_page_ready=True,receipt=receipt)
        self.assertEqual(updated.extra,((900405,6),));self.assertEqual(updated.forces,state.forces)
        self.assertIsNone(state.written(event,ordinary_page_ready=True).extra)
        wrong=M.UpdateReceipt(object(),event,1002,(900405,3))
        self.assertIsNone(state.written(event,ordinary_page_ready=True,receipt=wrong).extra)
        unknown=M.SkillSources(1001)
        self.assertIsNone(unknown.written(notice(0x6cb,struct.pack('>iiBiB',0,900405,6,0,0)),ordinary_page_ready=True).extra)

    def test_refusals_do_not_advance_and_bad_frames_do_not_modify_immutable_state(self):
        state=self.written(M.SkillSources(1001).constructed(),initial())
        rejected=(notice(0x131,struct.pack('>i',-1)+bytes(8)),
                  notice(0x123,struct.pack('>5i',-1,-1,0,-1,0)),
                  notice(0x6d1,struct.pack('>i',-1)+bytes(16)),
                  notice(0x484,struct.pack('>4i',-1,1,0,0)+U32(22)+bytes(252)))
        for event in rejected:self.assertIs(self.written(state,event),state)
        for raw in(initial().payload[:-1],initial().payload+b'\0',b'\0'*12):
            with self.assertRaises(ValueError):self.written(state,notice(0x55b,raw))
        bad=notice(0x131,bytes(4)+records(((25410,4),(25410,5)))+bytes(4))
        with self.assertRaises(ValueError):self.written(state,bad)
        self.assertTrue(state.matches(initial()))
        self.assertIs(self.written(state,initial(uid=1002)),state)
        with self.assertRaises(ValueError):state.matches(notice(0x6d1,initial().payload))

    def test_copied_owned_Force_inventory_allows_distinct_grades_of_same_skill(self):
        event,fields=copy_event(forces=M.ZERO_FORCE)
        owned=records(((100100,3),(100100,4),(100100,6)))
        raw=dict(fields)['0x14e']
        replacement=raw[:-15]+owned+b'\0'  # Replace the final one-record owned vector.
        updated=tuple((k,replacement if k=='0x14e'else v)for k,v in fields)
        packet=notice(0xd9,b''.join(v for k,v in updated)+b'other-current-copy-tail')
        receipt=M.bind_copy(packet,updated)
        self.assertEqual(receipt.preset.forces,M.ZERO_FORCE)
        self.assertEqual(M.SkillSources(1001).copied(receipt,packet).forces,M.ZERO_FORCE)
        duplicate=records(((100100,3),(100100,3)))
        bad=replacement[:-35]+duplicate+b'\0'
        with self.assertRaises(ValueError):M.copied_preset(bad)

    def test_archived_writer_changes_preserve_every_other_accepted_parent_byte(self):
        for filename,parent_sha,old,new in(
            ('skill_state.py','1795c52cbd77c073cde42d164c14d8d2a7733e175be6f160a9efccf528dc9ac0',
             b"if (character or {}).get('force_inventory'):",b'if character is not None:'),
            ('ordinary_skill_pages.py','5f0feff562b21efafae491013864c74321a9ff5ee385135d393b8b6ff5d079df',
             b"fixed+=vectors(character)if character.get('force_inventory')else bytes(8)",b'fixed+=vectors(character)')):
            raw=PATH.with_name(filename).read_bytes()
            if filename=='ordinary_skill_pages.py':
                binding=json.loads((PATH.parents[2]/'native-skill-production-writer-binding.json').read_bytes())
                row=next(r for r in binding['rows']if r['channel']=='online'and r['path']=='domain/'+filename)
                newline=b'\r\n'if b'\r\n'in raw else b'\n'
                for before,after in reversed(row['changes']):
                    encoded_after=after.encode().replace(b'\n',newline)
                    encoded_before=before.encode().replace(b'\n',newline)
                    self.assertEqual(raw.count(encoded_after),1)
                    raw=raw.replace(encoded_after,encoded_before)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),row['source_before_sha256'])
            self.assertEqual(raw.count(new),1)
            inverse=raw.replace(new,old,1)
            if filename=='ordinary_skill_pages.py'and b'\r\n'not in inverse:
                inverse=inverse.replace(b'\n',b'\r\n')
            self.assertEqual(hashlib.sha256(inverse).hexdigest(),parent_sha)


if __name__=='__main__':unittest.main()
