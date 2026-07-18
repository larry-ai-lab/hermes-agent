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
