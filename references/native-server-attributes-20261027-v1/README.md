# Native server attribute route — Issue593

The existing service sends naked B6 inputs and retains the previously accepted
V39/V40 components. This work completes a server-produced native attribute
notification without changing the client or adding a Hook. The current source
archive contains the implementations and portable native-result regressions;
live source assembly and gameplay acceptance are being completed before the
runtime profile selects this route.

`native_attribute_messages.py` encodes the complete original106 grammar.
`native_equipment_attributes.py` includes the original post-enhancement reforge
merge and the source-pinned0.4 alternate-mode coefficient.
`native_passive_attributes.py` and `native_attribute_projection.py` preserve
float32 source order, immutable percentage bases and the original small HP
epsilon. `native_attribute_snapshot.py` obtains the owned role, current title,
skill/force/guild/collection inputs and all attached item instances in one
read-only SQL transaction. It does not borrow cached projections or migrate
an optional table.
It also captures the selected ERP page, every saved page, profile metadata and
account progress under that same read transaction. The canonical allocation
writer must finish synchronization before this reader accepts an enabled
profile. A real two-page fixture verifies switching during an external commit;
missing metadata/pages and stale earned levels never become zero allocations.
The quest-role helper is deliberately narrow. Same-connection attachments add
the actual title/qualification, owned and equipped forces, visible traits,
ordinary-page metadata and LuCiel selector. Nonempty real-store fixtures and
an external multi-field commit verify those inputs independently of fresh
character defaults.

The native power modules retain the complete89B430 arithmetic and988320
normalization. The3F8 map uses the original `(probability, flag)` key so both
flags at the same threshold contribute independently. The conditional phase
ports all25 B26140 types, including native floorf/cap/epsilon behavior in the
qualified finite domain. Context offsets remain explicit until their full
producer is qualified; no omitted input becomes a plausible zero.

The option scalar source normalizes57 leaves, including shared MP restoration
before percentage conversion.136 independent original records agree across63
fields. The original five-field `STAT` dictionary uses `m_fBaseHP`; `m_fMaxHP`
is not that source property. Native scalar/data merging retains unscaled
capability fields, max aggregation, both phase modes and conditional branches.
The wrapper keeps its original phase order, including the data merge before
the class-line scalar predicate. The probability map preserves both flags at
the same threshold and the original zero-threshold fallback30. Capability-map
increments and additional-damage values retain their separate scaling rules.

The current15 ERP coefficient/cap/exclusion entries agree with the whole
original D36B90 Lua registration. Its registered manager feeds the whole
887F00 consumer in both modes;36 phase controls additionally cover dense,
absent, capped and overridden point indexes. The game constructor's guarded
scale defaults to1; caller-supplied later configuration still needs binding.

All70522 current definitions pass the scalar/metadata/map/condition/STAT
source compiler. All639 condition rows additionally pass the original property
body.128 native entry controls and108 duplicate/line/mode append controls
retain the separate qualification and contribution phases. The20 context
producer controls derive the25 condition types from the preceding aggregate;
B26830 writes attack data and extended scalars into separate records.
The copied condition category map is the preceding skill-damage map at778,
distinct from cooldown798. The second collector preserves9873F0/B23F70:
292 original controls qualify category/skill maps, both capability pair flags,
tag sets and integer resistance accumulation.84 property-body controls cover
their additional category/coefficient/resistance inputs. The four ordinary
category damage rates retain two rounded callback-weight multiplications.

The worn selector uses original wrapper+4 equipment slot codes. It must not
receive bag group9 in that field. All40170 combinations of195 current careers
and206 native required-class entries agree with the original class-entry
phase. The inherited74 original slot-side controls are retained. A private
frozen source additionally agrees with the whole cold worn collector in six
selector/resource controls; that evidence does not establish a live owner
context or complete set activation.
The immutable KIM-derived source contains all11422 set records and the shared
item property/option pools, without shipping a client binary. Every set lookup
and171722 threshold/qualifier boundary combinations agree with the original
6DB6A0/70F980 functions. These source-selection results remain distinct from
the caller's actual worn/color/activation qualification.

Portable tests include292 original passive/composition vectors, eight dense
original power vectors,251 condition vectors, 136 independent option scalar records,120 scalar merges,135 data merges,
120 combined wrapper cases,243 cooldown maps,84 power-map merges,
full wire contracts and a real
SQLite external-commit race. The independent native source investigations also
cover315 legal class/stage encodings and30722 original rank queries,15-family
SQL fixtures, and the original106 reader followed by guarded Unit/Actor
setters in both modes. These are controlled source/consumer proofs and do not
claim natural gameplay or a complete live dispatcher test.

The same-SQL capture now reads active pet identity, progression, accessories and
committed mount runtime without invoking mount settlement or login/schema
writers. Six real source controls cover nonempty state, concurrent commits,
ownership and expiry guards. Selected ERP allocations additionally pass a
60-query product106/original reader/point-map replacement chain; old points
are cleared before the selected page is applied.

The added immutable auxiliary sources cover all331 original pet templates,
932 titles,15 Master Artifacts and300 Collection definitions. Original loader
and collector controls include9480 pet branches,2796 title lookups and180
Artifact stage/potential branches. Pet gear contributes socket option IDs,
not equipment template IDs. Artifact's fourth potential is masked at stages3/4.
The Game+5F0 manager is independently identified as CX2ArtifactManager by RTTI
and ArtifactTemplet.lua loading; adjacent offsets are not riding-mount inputs.
All600 canonical CollectionData active/inactive cases pass the product encoder,
whole DB1080 reader and complete8A365F..8A3955 collector block, using the
unchanged GetTickCount import bound to its identical actual Windows export.

One real nonempty SQL fixture combines title ownership/deadline, pet and gear,
Master Artifact potentials and account Collection state in both modes. Its
arithmetic runs after releasing the read transaction and never reopens player
SQL. Deadline expiry invalidates the stale source; a fresh read removes only
the expired title's inputs. The four-group auxiliary assembler preserves the
original source order and remains separate from worn/set and active-buff
producers. It is not a claim that the whole collector or live path is enabled.

World-effect capture reuses the installed ordinary, supplement and economic
readers, including retained consumers and their exact source receipts. Actual
ONLINE and LOCAL six-group fixtures agree at one SQL generation and preserve
expiry boundaries without capture writes. Clock-only encoder metadata does not
enter the modifier digest. The same sampled validity time is passed to title,
pet and world-effect readers. An absent world schema avoids importing the
resource-heavy economic writer on cold character capture.
The base309 BuffManager definitions and927 explicit-active-vector controls are
retained as a source checkpoint. The additional INT75 definitions bring the
available registry to383 unique IDs. All384 original registrations retain the
existing1540 row;1153 original getter controls include a mixed ordered vector.
These checks cover the whole constructor, ID/socket property registration and
2DECA30 option getter. The notification dispatch independently identifies
3A2 ->2DEA410. Persisted elixir rows are not silently treated as the manager's
active vector; upstream global/unit buff qualification is a separate binding.

The immutable option-color index preserves all70522 records and288 distinct
type/Elianode/Artifact/Tenebrous/circuit color/shape profiles. Every profile
matches the original option property body. These color domains are separate:
the Elianode four-bin collector reads430, Artifact434 and Tenebrous470.
The fresh item constructor projection additionally matches71 original
DB4F80/7EBC80 controls across all33 groups, duplicate and zero values, the
18..21 first-nonempty priority and the803..806 derived socket selection.
It explicitly requires the canonical writer's empty legacy mutation map.

Canonical saved item bindings now supply scalar defaults from that exact
writer seed, immutable template pools, source-only option vectors and the
separate colors. A private22-item source agrees with12 whole native worn/set
compositions and six canonical-binding controls. Three of the latter decode
the installed main equipment DTO with fishing map keys39..42 through whole
DB0AC0. Group24 is Master Artifact equipment, gated by Artifact evolution;
ordinary costumes remain in group9. The tested cold owner/preset and empty
secondary/registration controls do not claim a complete live owner lifecycle.

The three post-power Forces900407/900410/900411 now have200 whole89C9D0
controls, including the original rank/definition/numerical getters and floorf.
All five current source ranks and eight eligibility combinations retain the
native threshold, cap and mixed float/double rounding. Their prepared rank
indexes are explicit phase controls, separate from the final live SQL binding.

The capability-row producer now preserves the original six append gates,
required factor/nonzero level and signed float32 accumulation. All833 distinct
current source profiles,33 boundary controls and46 full source-to-second-merge
chains agree with the original parser and both base/INT factor registries.
Packed regressions caught and fixed negative zero being lost by a default-value
shortcut; the original failed comparison and superseded receipts remain local.

The MP limit phase retains the exact order of66 skill sources and the original
300 base, equipment, rate, flat and extension contributions.414 whole895790
controls include original rank/definition/numerical readers in both phase modes.
Its separate1984460 equipment collector has534 whole native controls, including
slot-side, all selectors, both additional-item modes, exclusions and duplicates.
All181836 current templates contain finite MP fields;267 are nonzero with actual
values5/20/30. This MP selector differs from the general worn selector when
selector2 is used. Corrupt stored wrappers or added items without a template
are rejected before entering a native state that dereferences them.
A further96 whole895790 chains combine current nonzero equipment MP and ERP17
allocations/caps/overrides with both skill source modes and replacement vectors.
The prepared rank context remains distinct from the live character lifecycle.

The Unit3940 CP factor is now sourced from the original89C6D0 leaf and
ItemTierData's three binary64 coefficients.128 current set-threshold chains
qualify activation before individual effect-entry gates; eight leaf controls
retain sorted unique IDs, identity1 for absent definitions and double precision.
All three registrations and the original first-registration retention execute.

The class attack-kind map is generated by the original current relative-stat
registry. Its120 second/third-class entries select physical or magical by
float32 coefficients, with ties selecting2.75 current base/first classes retain
the original missing-entry path.585 original CP branch controls connect all195
classes to the actual registered map. Resource loading and Lua script-service
closures remain outside this table-registration phase proof.

The per-item option collector now has277 original wire/constructor/collector
controls covering all33 saved groups, source order, duplicates, zero values,
template versus character level and conditional group gates. It uses the exact
canonical trailing uint64 source for the circuit-state default; nonzero test
overrides remain explicit qualification controls.

The ordinary callback's51-scalar/13-data subset has154 whole88A180 controls,
including nonempty capability/probability/additional maps and conditional stat
rows. Six whole988D70 controls establish its separate pre-merge scaling and
unscaled11C leaf. PvP level-linked sources bypass callback weight; rank-linked
and PvE-rank-linked paths have distinct pre-scaling and PvP-rate behavior.
Five distinct current metadata profiles span all70522 definitions, with20
source-parser-to-whole-callback comparisons. Prepared rank/class contexts,
other scalar leaves and actor event-effect containers are separate contracts.

Independent composition of a private22-item source now reproduces25 callbacks
per pass from saved fields, template pools, set selection and the title source.
It matches the full original897100/8889F0 collectors in their qualified cold
context, using the complete858ED0..859402 Unit initialization prefix and real
inventory owner/caches. The original constructor initializes67 extra inventory
slots; these are traversed rather than replaced with an empty zeroed object.
This composition caught a missing source default: absent or Lua-nil probability
direction is1.32 new original parser/merge controls cover that default and
explicit0/1. First51 scalar leaves,13 data leaves and relevant CP maps now
agree, as do second-pass category/capability maps. Private player inputs and
native temporary pointers remain outside Git; full CP/lifecycle is separate.

Learned flat STAT collection now follows the complete8F8D50 channel ordering.
Nine original9BFE30 controls cover all five distinct profiles in the current
4483 skill definitions, including four nonempty STAT definitions, plus nil and
unequal-vector controls.63 whole-collector comparisons cover types, rank bounds,
selected-page gates, duplicate extra entries and missing templates. An invalid
selected page skips both later channels; a valid empty selected map still
permits the extra channel. Unsafe unchecked main-channel source rows are
rejected before calculation. Current ownership and preset lifecycle remain
separate source contracts, rather than invented empty inputs.

The integer maximum-MP option leaf now preserves its distinct conversion
rules: source m_iAddMpValue, float32 pre-scaling, cvttss2si truncation, and
float32 accumulation followed by a second signed32 conversion.132 whole
original callback controls include rank/PvE-rank, entry/class gates and
signed32/float32 boundaries. The current84 reforge stat registrations also
execute through the whole original setter;8118 complete getter comparisons
cover all369 admitted templates and levels0..21.

The private complete888CA0/896870/89B430 chain now executes with the unchanged
current CharacterStatTable KL bytecode and original math library, source
reforge registration, typed Unit prefix, consistent complete definition caches
and original skill DTO producers. An independent saved-source composition
matches both full kernel outputs, every kernel scalar/map, final seven and MP
in both modes for one frozen source. Earlier incomplete-context results remain
retained failures/controls. This still leaves live source/lifecycle acceptance
before runtime selection and publication.

The remaining integration must bind every actual modifier/context and CP
aggregate, qualify the current HP clamp/refresh lifecycle in the unmodified
client, then enable and publish in the ordinary queue from the actual latest
ONLINE/LOCAL parents.106 always includes CP; zero is not a preservation
sentinel. Equipment totals must never replace naked B6 inputs. No player data,
runtime image, raw capture, authentication material or production configuration
is included here.
