# Explicitly Out of Scope

There is no v1/v2 staging in this plan — everything in [`01-requirements/08-scope.md`](../01-requirements/08-scope.md) ships together. The items below are **not deferred; they are deliberately excluded** from this product. Re-opening any of them is a product decision, not a backlog pull.

| Excluded | Why |
|----------|-----|
| Post-generation video editing (trims, cuts, transitions, timeline) | The script is the editing surface; a timeline editor is a different product. Scene re-render + swap-image cover the practical fix-up cases. |
| Languages beyond Hindi/English | Bengali dropped 2026-07 by owner decision to shrink the quality/test matrix. Architecture is language-pluggable (edge-tts voices + Noto fonts + prompt directive), so adding one later is cheap — but it is not in this build. |
| Mixed mode (avatar intro + image b-roll) | Owner locked exactly two modes; a third hybrid mode multiplies the assembly/test matrix. |
| Direct auto-posting to YouTube/Instagram | OAuth app review processes, token storage liability, and platform API churn for marginal value over "download and upload". |
| Localized (Hindi) UI chrome | Script *content* is fully bilingual; UI copy stays English. Cheap to revisit. |
| Payments / paid tiers | The product's identity is free. Nothing in the architecture assumes billing. |
| Native mobile apps | The site is responsive; rendering happens server-side anyway. |
