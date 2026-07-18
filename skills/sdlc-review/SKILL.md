---
name: sdlc-review
description: Native Kanban review-lane decision contract for implementation artifacts.
version: 1.0.0
---

# SDLC Review

Use this only for a Kanban task claimed from the native `review` status.
Review the actual scoped diff, declared artifacts, and verification evidence; a
PR is optional and must not be assumed.

Return exactly one durable route:

- `PASS` — call `kanban_complete` only after evidence supports acceptance.
- `REVISE` — return the same task to its recorded writer using the native
  review-revise transition. Do not create a duplicate child or fixback chain.
- `NEEDS_APPROVAL` — call `kanban_block` with the concrete approval boundary.
- `UNSAFE` — call `kanban_block` with the unsafe condition and evidence.

Fail closed when the workspace, claimed reviewer identity, artifact evidence,
or required approval is missing. A review decision never authorizes merge,
publish, deployment, credentials, or any external side effect.
