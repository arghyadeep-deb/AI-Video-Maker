# Script Review Loop

**Question.** How much control does the user have over the script before rendering?

**Decision.** Total control. Four actions, repeatable in any order, and **nothing renders until Accept**.

## The four actions (locked)

| Action | Behavior |
|--------|----------|
| **Accept** | Script version is frozen; user proceeds to mode choice. |
| **Scrap** | Whole script discarded; back to the description input (description pre-filled for tweaking). |
| **Improve selection** | User selects any span of text + optionally types an instruction ("make this funnier", "add a hook"). AI rewrites **only the selection**, in the same language. Replacement is shown as a keep/revert diff before applying. |
| **Manual edit** | Inline editing of any scene's text, no AI involved. |

## Loop rules

- **Selection-scoped means selection-scoped.** The improve call sends the full script as context but the model may only return replacement text for the selected span. Other scenes must be byte-identical after the operation.
- Improvements always come back in the script's language.
- Every applied change (AI or manual) creates a new **script version** row; the last 10 versions are kept so the user can undo (single-level undo in UI; full history in DB).
- Scrap requires a confirm click (destructive).
- The visual_hint of an edited scene is regenerated lazily at generation time if its text changed (cheap batch call), not on every keystroke.

## Why a diff on AI improvements

The user asked for the ability to reject bad improvements without losing their place. Showing old → new for the selection and letting them keep/revert makes the AI a proposal engine, never an overwriter.

Design: [`03-design/03-review-loop-design.md`](../03-design/03-review-loop-design.md). Diagram: [`05-flowcharts/03-script-review-loop.mmd`](../05-flowcharts/03-script-review-loop.mmd).
