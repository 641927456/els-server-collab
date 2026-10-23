# Native wardrobe hair and weapon positions

The server had reversed the current client's native equipment positions: weapon is `EP_WEAPON_HAND=2`, while hair is `EP_DEFENCE_HAIR=6`. A real permanent hair item could consequently fail with the hair palette, while incorrect palette, ticket or hanger-scroll classifications were accepted for the opposite part.

The correction uses the existing native part definitions. It fixes the part and target lists of 14 already-qualified wardrobe tickets, selects the hair dye palette for position6, and assigns weapon/accessory hanger removal to scroll294546 and hair/body/legs to scroll294547. All other 31 qualified ticket definitions are preserved. Existing UID ownership, qualification, transactional consumption, receipts and cold restoration remain authoritative on the server. Rendering and dye effects stay in the client.

Controlled source/SQL checks reproduced the old failure with actual hair81025 and weapon332700, then verified the corrected palettes, ticket lists and scrolls. Authenticated private TLS checks covered both complete composed runtime trees, cross-part refusal without economic changes, successful one-unit consumption and cold restoration. Source review confirmed that the 19 original unknown ticket definitions and all588 held dye entries were unchanged. Newly discovered ticket-name variants are not silently admitted by this correction.

Release `appearance-config-core-20261021-v1` passed public pinned-TLS acceptance with finite controlled QA items: eight successful dye/register/removal/ticket operations and six cross-part refusals, exact consumption, unchanged ED/experience, and cold restoration. The same dedicated QA account was disabled afterwards; prior account rows and the registration configuration were preserved. An initial oversized SSH helper was rejected locally before wardrobe submission, then uploaded by verified SHA and resumed on that same account; previous failures remain in the private evidence.

This change does not add drop, shop, event or GM acquisition sources, remove conditionally hidden restrictions, admit unknown special instances, modify the client, or claim full natural GUI acceptance.
