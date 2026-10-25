# Tutorial admission HP-interface compatibility

The tutorial subclass initializes its own lightweight catalog instead of the
ordinary dungeon constructor. After the ordinary HP refactor, inherited code
reads `hp_context` and `catalog.static_npc_level`, so fresh tutorial admission
raises an AttributeError before the native loading sequence completes.

Two small changes explicitly disable the ordinary HP capability for tutorial
graphs and preserve their existing spawn-seed level. Existing tutorial HP data,
quests, rewards, inventory and ordinary C1 HP behavior remain unchanged.

Validation covers the original two missing-interface failures, all 15 tutorial
graphs and their source stages, and real private Application transports for
four character roots with fresh/cold reconnects. The native 60/61/14A/91/B2/B3/BD
sequence completes without quest, inventory or balance changes. No client,
schema, migration or economic change is included. Natural GUI/combat and
protected deployment are separate from this source candidate.

Stacked on PR #467 at `4818abc12e9b53d0a56154008e427ea4c818ae1b`.
Fixes #468 after review. This source push does not deploy a server.
