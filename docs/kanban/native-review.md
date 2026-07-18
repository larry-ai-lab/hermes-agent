# Native Kanban review lane

Native review is an explicit, durable writer/reviewer handoff. A writer runs:

```bash
hermes kanban submit-for-review TASK_ID --summary "implementation and test evidence"
```

The transition is run-id guarded for dispatcher workers and retry-safe: a duplicate submission cannot create a second reviewer run. A reviewer either closes the active review run with `complete`, or returns it to the captured writer with:

```bash
hermes kanban revise TASK_ID --reason "concrete failing acceptance criterion"
```

Gateway dispatch is opt-in, so existing boards are not changed by an upgrade:

```yaml
kanban:
  native_review_enabled: true
  native_review_shadow: false
```

`native_review_shadow: true` emits a deterministic, read-only candidate report; it never claims, spawns, or changes a review card. Before a real claim, the dispatcher verifies both the reviewer profile and canonical `sdlc-review` skill. Missing prerequisites retain the `review` row and generate one `review_dispatch_blocked` audit event rather than entering a spawn loop.
