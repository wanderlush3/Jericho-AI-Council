---
description: Run a Stillwind-managed coding session for this project
---

This project is managed by the **Stillwind Workflow** tool (`sw`).
When starting a coding session, follow the protocol below.

## Session Protocol

// turbo-all

1. Check project status:
```
sw --project . status
```

2. Review feature backlog:
```
sw --project . features
```

3. Read `progress_log.md` for institutional memory — understand what was done in previous sessions and any advice left for you.

4. Identify the **next eligible feature** from the status output (pending, with all dependencies met).

5. Implement **exactly one feature** per session. Follow the A-through-E protocol:
   - **Step A**: Context loading (read progress log, git history, verify tests pass)
   - **Step B**: Feature selection (the one identified in step 4)
   - **Step C**: Implementation (write code, write tests)
   - **Step D**: Review sweep — run `sw --project . review` on the codebase
   - **Step E**: Handoff — update `features.json` status to `completed`, append a structured session entry to `progress_log.md`, commit with `feat(scope): message [F-XXX]` format

6. Run the full test suite to verify no regressions:
```
python -m pytest tests/ -v --tb=short
```

7. After completing the feature, update:
   - `features.json` — set the feature status to `completed`
   - `progress_log.md` — append a session entry with: Summary, Technical Debt, Advice for Next Agent

## Key Rules

- **Single-feature discipline**: One feature per session. No scope creep.
- **Never delete progress_log.md entries**: They are institutional memory for future agents.
- **Structured commits**: Use `feat(scope): message [F-XXX]` format.
- **Tests required**: Every feature must include tests. Run the full suite before and after.
- **Leave advice**: Always write "Advice for Next Agent" so the next session has context.
