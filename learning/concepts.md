# Concepts

Record durable understanding, not every definition encountered.
## 2026-09-30: MVVM Commands & CommandParameter in .NET MAUI

- **Concept:** Instead of code-behind click events, buttons bind to `ICommand` in the ViewModel.
- **Key takeaway:** `new Command<string>(OnDigit)` paired with `CommandParameter="7"` allows a single command to handle multiple buttons dynamically.
- **Related concepts:** MVVM, Data Binding, ICommand, Separation of Concerns.

## 2026-09-30: MAUI Layouts — StackLayout vs Grid

- **StackLayout (Vertical/Horizontal):** Places elements in a continuous line. Elements shrink or expand to fit their text length (`Auto` behavior).
- **Grid:** Divides space into Columns and Rows with 0-based indexing (`Grid.Column="0"`).
- **Star Sizing (`*`):** `ColumnDefinitions="*, *"` allocates equal proportional shares of available space (50% each), keeping UI controls stable.

## 2026-09-29: .NET Event Pattern (object sender, EventArgs e)

- **Learner's explanation:** `sender` tells you who triggered the event, and `e` tells you what changed or was passed along.
- **Key takeaway:** The `object` type allows any control to reuse the same handler signature; specialized `EventArgs` (like `TextChangedEventArgs`) supply event-specific data.
- **Example:** `private void OnResetClicked(object sender, EventArgs e)`
- **Related concepts:** Event handlers, Polymorphism, Data Binding.


## YYYY-MM-DD: Concept

- **Learner's explanation:**
- **Corrected understanding:**
- **Example:**
- **Related concepts:**
