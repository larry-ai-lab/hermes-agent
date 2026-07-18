"""Native review lane: durable writer/reviewer boundary regression tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def review_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()


def test_submit_review_is_durable_and_separates_reviewer(review_db: None) -> None:
    with kb.connect() as conn:
        task_id = kb.create_task(conn, title="implementation", assignee="spark")
        assert kb.claim_task(conn, task_id)
        run_id = kb.get_task(conn, task_id).current_run_id
        assert kb.submit_for_review(
            conn, task_id, summary="implemented", metadata={"tests": 1},
            expected_run_id=run_id,
        )
        task = kb.get_task(conn, task_id)
        assert task.status == "review"
        assert task.assignee == "default"
        assert task.writer_assignee == "spark"
        assert task.reviewer_assignee == "default"
        # Native transition is idempotent and does not synthesize a second run.
        assert not kb.submit_for_review(conn, task_id, summary="duplicate")
        assert kb.claim_review_task(conn, task_id)
        reviewer_run_id = kb.get_task(conn, task_id).current_run_id
        assert reviewer_run_id != run_id
        assert kb.complete_task(conn, task_id, result="PASS", expected_run_id=reviewer_run_id)
        assert kb.get_task(conn, task_id).status == "done"


def test_review_revise_returns_to_original_writer_without_child(review_db: None) -> None:
    with kb.connect() as conn:
        task_id = kb.create_task(conn, title="implementation", assignee="spark")
        assert kb.claim_task(conn, task_id)
        assert kb.submit_for_review(conn, task_id)
        assert kb.claim_review_task(conn, task_id)
        review_run_id = kb.get_task(conn, task_id).current_run_id
        assert kb.revise_from_review(conn, task_id, reason="fix test", expected_run_id=review_run_id)
        task = kb.get_task(conn, task_id)
        assert task.status == "ready"
        assert task.assignee == "spark"
        assert task.writer_assignee == "spark"
        assert not kb.revise_from_review(conn, task_id, reason="duplicate")


def test_true_block_does_not_enter_review(review_db: None) -> None:
    with kb.connect() as conn:
        task_id = kb.create_task(conn, title="blocked", assignee="spark")
        assert kb.claim_task(conn, task_id)
        assert kb.block_task(conn, task_id, reason="needs credentials")
        assert kb.get_task(conn, task_id).status == "blocked"
        assert not kb.submit_for_review(conn, task_id)


def test_shadow_review_is_deterministic_and_does_not_mutate(review_db: None) -> None:
    with kb.connect() as conn:
        task_id = kb.create_task(conn, title="implementation", assignee="spark")
        assert kb.claim_task(conn, task_id)
        assert kb.submit_for_review(conn, task_id)
        before = kb.get_task(conn, task_id)
        result = kb.dispatch_once(conn, native_review_enabled=False, native_review_shadow=True)
        assert result.review_shadow == [{"task_id": task_id, "assignee": "default", "reviewer_assignee": "default"}]
        after = kb.get_task(conn, task_id)
        assert after.status == before.status == "review"
        assert after.current_run_id == before.current_run_id


def test_missing_review_prerequisite_audits_without_claim_loop(review_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kb, "_review_prerequisite_error", lambda _: "canonical review skill unavailable")
    with kb.connect() as conn:
        task_id = kb.create_task(conn, title="implementation", assignee="spark")
        assert kb.claim_task(conn, task_id)
        assert kb.submit_for_review(conn, task_id)
        first = kb.dispatch_once(conn, native_review_enabled=True)
        second = kb.dispatch_once(conn, native_review_enabled=True)
        events = conn.execute("SELECT kind FROM task_events WHERE task_id=? AND kind='review_dispatch_blocked'", (task_id,)).fetchall()
        assert task_id in first.skipped_nonspawnable
        assert task_id in second.skipped_nonspawnable
        assert len(events) == 1
        assert kb.get_task(conn, task_id).status == "review"
