---
name: daily-tasks
description: >
  Write and complete Marvin vault tasks using checkbox and TODO syntax that
  find_incomplete_tasks and complete_task can parse. Use when planning the day,
  listing todos, checking off tasks, or appending tasks to a daily note.
---

# Daily tasks skill

Marvin’s vault tools recognize incomplete work only in specific line forms. When
you create or edit tasks, use these patterns so later “check that off” requests work.

## Preferred form (checkbox)

```markdown
- [ ] Call dentist
* [ ] Buy groceries
+ [ ] Ship release notes
```

Incomplete markers Marvin accepts inside brackets: space, `/`, `todo`, `TODO`,
`next`, `Next` (for example `- [TODO] Draft outline`).

Completed form after `complete_task`:

```markdown
- [x] Call dentist
```

## Also accepted (plain TODO / NEXT lines)

```markdown
TODO: Email the landlord
NEXT: Review budget
Action item: File expense report
```

Prefer checkboxes for new tasks. Use TODO/NEXT only when matching an existing note style.

## Planning workflow

1. Use vault tools to read today’s daily note (or create it) before inventing a plan.
2. Append **new** incomplete checkbox lines; do not replace the whole note unless asked.
3. One actionable item per line. Keep the body short and concrete.
4. Do not turn narrative paragraphs into fake tasks.
5. Never mark a task complete in prose alone — call `complete_task` (with write
   authorization) so the file flips `[ ]` → `[x]`.
6. If nothing matches, say so; do not invent a completed task.

## Examples

Good append:

```markdown
## Tasks
- [ ] Prep standup notes
- [ ] Review PR #42
```

Bad (tools will not find these as incomplete tasks):

```markdown
Need to prep standup and review the PR later.
☐ Prep standup
```
