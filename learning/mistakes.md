# Mistakes

Record meaningful bugs or recurring misconceptions. Preserve the original reasoning.
## 2026-09-30: Boolean Condition Over-specification in State Flags

- **Problem:** Writing `if (DisplayText == "0" && IsNewEntry)` failed when overwriting numbers after an operator, because `DisplayText` was not `"0"`.
- **Mistake:** Combining state flags with existing content checks using `&&`.
- **Correct mental model:** A dedicated transition flag like `IsNewEntry` already fully represents the state ("ready for a new number"), regardless of what text is currently displayed.
- **Category:** Logic / State Machine

## 2026-09-29: Missing Braces in Conditional Blocks

- **Problem:** Warning text was displayed, but the text color was always green instead of red.
- **Mistake:** Omitted `{ }` on an `else` branch that had two statements.
- **Original mental model:** Indented lines below `else` belong to the `else` block.
- **Correct mental model:** Without `{ }`, C# only attaches the single next statement to `else`; all subsequent statements execute unconditionally.
- **Category:** Syntax / Scope
- **Prevention:** Always wrap `if` and `else` blocks in `{ }`, even for single lines.

## YYYY-MM-DD: Short title

- **Problem:**
- **Mistake:**
- **Original mental model:**
- **Correct mental model:**
- **Category:**
- **Prevention:**
- **Follow-up exercise:**
