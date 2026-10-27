# Ordinary learning: five missing Elesis passives

Issue594: current trees for Dark Knight35, Crimson Avenger125 and Bloody Queen173 still reference28410/28411/28413/28414/28429. The deployed skill learner rejects every definition with nonzero SP metadata, leaving these native passives absent even at99 with the appropriate seal unlocked. The same records feed town55B and dungeon member skill data, so this is an input omission before native damage/recovery/cooldown consumers.

[The official Season2 learning change](https://elsword.koggames.com/season-2-elsword-rena-reborn/revampoverview.html) makes ordinary learning/upgrades automatic and free, with passive ranks following character level. Locked skills remain locked until their unlock is owned. The current pinned catalog supplies the exact class trees, rank levels, stage requirements and passive numerical definitions; the patch does not replace those numerical effects.

The candidate removes only the SP filter inside the existing ordinary-tree category and seal checks. Relationship/core/guild categories, class/tree membership, level/stage limits, upgrade deletion and sealed28414 remain governed by the existing rules. No client script, runtime Hook, EXE/KOM or player database changes are included.

Validation against the actual formal catalog:1305 controlled role cases, including all315 legal class/TC/Master flag states, plus1980 town/dungeon learned-vector encodings. Original missing records reproduced for all3 affected classes; all other learned and active records are unchanged. Portable tests cover all5 passives, rank boundaries, seal denial and unrelated-character/category denial. This is source/protocol qualification, not full native effect qualification.

The source under references/native-modern-auto-learning-20261027-v1 is a candidate and is deliberately absent from current-engine.json. Existing V40 is retained. Native record/effect acceptance and full-skill gameplay remain pending; no installation is claimed by this source review.
