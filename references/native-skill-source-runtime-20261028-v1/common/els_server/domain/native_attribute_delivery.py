"""Owned106 delivery ordering after ordinary replies, outside account math.

One transport operation lock owns each cursor. Only successfully written server
batches enter observe_sent; building/encoding a batch is not a delivery receipt.
The caller separately validates the source lease, account/selection/scene graph
and readiness through the serialized business worker before preparing a plan.
This component does not select a channel, infer source values or open a socket.
"""
from dataclasses import dataclass,replace
import math
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain import native_skill_delivery_sources as skill_sources
from els_server.domain import native_attribute_readiness as readiness


@dataclass(frozen=True)
class ActorEpoch:
    owner_uid: int
    account_id: int
    unit_type: int
    serial: int


@dataclass(frozen=True)
class DeliveryPlan:
    epoch: ActorEpoch
    revision: int
    events: tuple
    valid_before: object


def _clock(at):
    if type(at) not in (int,float) or not math.isfinite(at):
        raise ValueError('Native attribute delivery clock required')


class DeliveryCursor:
    def __init__(self):
        self.epoch = None
        self.revision = 0
        self._serial = 0
        self._reset()

    def _reset(self):
        self._copied = False
        self._actor_ready = False
        self._ui_ready = False
        self._skills = None
        self._active = None
        self._style = None

    def begin(self, owner_uid, account_id, unit_type):
        if (type(owner_uid) is not int or not 1001 <= owner_uid < 2**63
                or type(account_id) is not int or not 0 < account_id < 2**63
                or type(unit_type) is not int or not 1 <= unit_type <= 15):
            raise ValueError('Owned current native Actor identity required')
        self._serial += 1
        self.epoch = ActorEpoch(owner_uid, account_id, unit_type, self._serial)
        self.revision += 1
        self._reset()
        self._skills = skill_sources.SkillSources(owner_uid)
        return self.epoch

    def relocate(self, epoch):
        """A new scene needs readiness/restoration again; it keeps the owned Unit."""
        if epoch is not self.epoch:
            return None
        copied, skills, ui_ready = self._copied, self._skills, self._ui_ready
        current = self.begin(epoch.owner_uid, epoch.account_id, epoch.unit_type)
        self._copied = copied
        self._skills = skills
        self._ui_ready = ui_ready
        return current

    def discard(self):
        self.epoch = None
        self.revision += 1
        self._reset()

    @staticmethod
    def _owned(event, epoch, *, offset=0):
        return (len(event.payload) >= offset+8
                and struct.unpack_from('>Q', event.payload, offset)[0] == epoch.owner_uid)

    def observe_sent(self, epoch, events, *, actor_ready, copies=(), skill_updates=(), ui_receipts=(), ordinary_page_ready=None):
        """Commit exact written sources and current6E9→6EA UI evidence.

        Actor readiness is separate. A new own2A clears skill-UI readiness;
        same-Unit scene relocation preserves it. An optional legacy page flag
        may restrict application, but never grants the missing native UI gate.
        """
        if (type(events) is not tuple or type(actor_ready) is not bool
                or type(copies)is not tuple or type(skill_updates)is not tuple or type(ui_receipts)is not tuple
                or ordinary_page_ready is not None and type(ordinary_page_ready)is not bool):
            raise ValueError('Immutable written server batch and explicit readiness required')
        if epoch is not self.epoch or epoch is None:
            return False
        # UID-less replies require the producer's owned selection epoch, not
        # merely discovery in a mailbox after selection changed. The caller
        # supplies only replies captured for this epoch at business completion.
        # Every source proof must bind the exact Event object actually written.
        if (any(type(proof)is not skill_sources.CopyReceipt or proof.owner!=epoch.owner_uid
                or not any(proof.event is event for event in events)for proof in copies)
                or len({id(proof.event)for proof in copies})!=len(copies)
                or any(type(proof)is not skill_sources.UpdateReceipt
                    or proof.epoch is not epoch or proof.owner!=epoch.owner_uid
                    or type(proof.event)is not Event or proof.event.event_id!=0x201
                    or proof.event.kind not in(0x131,0x123,0x6d1,0x484,0x6cb,0x6cf)
                    or not any(proof.event is actual for actual in events)for proof in skill_updates)
                or len({id(proof.event)for proof in skill_updates})!=len(skill_updates)
                or any(type(proof)is not readiness.SkillUIReceipt
                    or proof.epoch is not epoch or proof.owner!=epoch.owner_uid
                    or type(proof.request)is not Event or proof.request.event_id!=0x202
                    or proof.request.kind!=0x6e9 or proof.request.payload!=b''
                    or proof.request.performers not in((),(0,)) or proof.request.payload_mode!=0
                    or proof.request.uid!=2**64-1 or proof.request.target_uid!=2**64-1
                    or type(proof.request_sequence)is not int or not 1<=proof.request_sequence<2**32
                    or type(proof.reply)is not Event or proof.reply.event_id!=0x201
                    or proof.reply.kind!=0x6ea
                    or not any(proof.reply is actual for actual in events)for proof in ui_receipts)
                or len({id(proof.reply)for proof in ui_receipts})!=len(ui_receipts)):
            raise ValueError('Exact owned written skill source evidence required')
        # Apply to locals first so one malformed owned restoration cannot partly
        # advance the cursor. Other owners' peer packets do not satisfy this Unit.
        copied, skills, active, style = self._copied, self._skills, self._active, self._style
        ui_ready = self._ui_ready
        for event in events:
            if type(event) is not Event:
                raise ValueError('Original server Event required')
            if event.event_id != 0x201:
                continue
            if event.kind == 0x2a:
                # Current2A is result:i32 + Unit; Unit UID is at wire offset9.
                if event.payload[:4] == bytes(4) and self._owned(event, epoch, offset=13):
                    copied, active, style = True, None, None
                    ui_ready = False
                    # Do not infer native constructor zeros from a2A kind.
                    skills = skill_sources.SkillSources(epoch.owner_uid)
                    proof=next((p for p in copies if p.event is event),None)
                    if proof is not None:skills=skills.copied(proof,event)
            elif event.kind == 0xd9 and self._owned(event,epoch,offset=9):
                proof=next((p for p in copies if p.event is event),None)
                if proof is not None:skills=skills.copied(proof,event)
                else:
                    # Unknown copied Force inputs cannot attest old sources.
                    skills=replace(skills,forces=None,extra=None)
            elif event.kind == 0x6ea:
                proof=next((p for p in ui_receipts if p.reply is event),None)
                if proof is not None:ui_ready=proof.current()
            elif event.kind == 0x55b and self._owned(event, epoch):
                skills = skills.written(event,ordinary_page_ready=ui_ready)
            elif any(event is proof.event for proof in skill_updates):
                proof=next(proof for proof in skill_updates if proof.event is event)
                # A legacy True flag can no longer grant readiness. False is
                # an optional additional restriction while callers migrate.
                skills = skills.written(event,ordinary_page_ready=ui_ready and ordinary_page_ready is not False,receipt=proof)
            elif event.kind==0x131:
                skills=replace(skills,learned=None,unsealed=None)
            elif event.kind in(0x6d1,0x484):
                skills=replace(skills,forces=None)
            elif event.kind in(0x6cb,0x6cf):
                # These UID-less ownership consumers change the independent
                # extra vector. Never keep an old calculation across an
                # unqualified producer/selection update.
                if len(event.payload)<4 or event.payload[:4]==bytes(4):
                    skills=replace(skills,extra=None)
            elif event.kind in (0x4e3,0x70b) and self._owned(event, epoch):
                limit = 1 if event.kind == 0x4e3 else 2
                if len(event.payload) != 9 or event.payload[8] > limit:
                    raise ValueError('Canonical owned LuCiel restoration required')
                if epoch.unit_type != 10:
                    raise ValueError('LuCiel restoration targets a different unit family')
                if event.kind == 0x4e3: active = event.payload[8]
                else: style = event.payload[8]
        self._copied, self._skills, self._active, self._style = copied, skills, active, style
        self._actor_ready = actor_ready
        self._ui_ready = ui_ready
        self.revision += 1
        return True

    def prepare(self, epoch, *, skills, extra_skills, attribute, active, style, valid_before, at):
        """Append needed LuCiel restores, then106, without consuming state.

        skills is the same-snapshot canonical55B source comparison. Its rank
        sources must already match the normal copies/initialization/incremental
        notices actually written. Repeating55B is not an inert
        prerequisite: whole13A34F0/8F67D0/977EC0 clears an original slot field.
        Ordinary ranks, unsealed IDs and Force inputs have separate consumers;
        an empty Force vector retains entries, while explicit zeros clear them.
        Trait/action/context dependencies remain the source factory's contract.
        LuCiel defaults are explicit UID+byte notices, including zero.
        """
        _clock(at)
        if epoch is not self.epoch or epoch is None or not self._copied or not self._actor_ready or not self._ui_ready:
            return None
        if valid_before is not None:
            _clock(valid_before)
            if at >= valid_before:
                return None
        if (type(skills) is not Event or skills.event_id != 0x201 or skills.kind != 0x55b
                or not self._owned(skills, epoch)):
            raise ValueError('Same-owned canonical55B required before native attributes')
        if (type(attribute) is not Event or attribute.event_id != 0x201 or attribute.kind != 0x106
                or not self._owned(attribute, epoch, offset=1)):
            raise ValueError('Same-owned encoded native106 required')
        if not self._skills.matches(skills)or not self._skills.matches_extra(extra_skills):
            return None
        messages = []
        if epoch.unit_type == 10:
            if type(active) is not int or active not in (0,1) or type(style) is not int or not 0 <= style <= 2:
                raise ValueError('Complete same-snapshot LuCiel preferences required')
            from els_server.protocol.luciel_messages import active_notification,notification
            if active != self._active: messages.append(active_notification(epoch.owner_uid, active))
            if style != self._style: messages.append(notification(epoch.owner_uid, style))
        elif active is not None or style is not None:
            raise ValueError('Non-LuCiel source must not send LuCiel preferences')
        messages.append(attribute)
        return DeliveryPlan(epoch, self.revision, tuple(messages), valid_before)

    def current(self, plan, *, at):
        _clock(at)
        return (type(plan) is DeliveryPlan and plan.epoch is self.epoch
                and plan.revision == self.revision and self._copied and self._actor_ready and self._ui_ready
                and (plan.valid_before is None or at < plan.valid_before))

    def sent(self, plan):
        """Commit after complete transport write, under the same operation lock.

        Source validity was checked immediately before writing. Wall time may
        advance during a socket write; receipt records delivery, not a client ACK.
        A partial/failed write must leave this method uncalled and close its
        transport. No prepared plan advances a newer selection or scene.
        """
        if type(plan) is not DeliveryPlan or plan.epoch is not self.epoch or plan.revision != self.revision:
            return False
        return self.observe_sent(plan.epoch, plan.events, actor_ready=self._actor_ready)
