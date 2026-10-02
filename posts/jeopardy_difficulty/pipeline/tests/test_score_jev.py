import hashlib
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from pipeline.score_jev import (
    score_clue, build_prompt, filter_scoreable,
    _load_checkpoint, _cleanup_checkpoint, _clue_key, PROMPT_PATH,
)


def test_build_prompt_fills_clue_fields():
    result = build_prompt(category="SCIENCE", clue="It orbits Earth", answer="the Moon")
    assert "SCIENCE" in result
    assert "It orbits Earth" in result
    assert "the Moon" in result


def test_build_prompt_clue_format_is_self_contained():
    """Clue state must include all three fields without reading prompt.txt."""
    result = build_prompt(category="HISTORY", clue="She led France", answer="Joan of Arc")
    assert "HISTORY" in result
    assert "She led France" in result
    assert "Joan of Arc" in result


def test_filter_scoreable_excludes_media():
    df = pd.DataFrame({
        "media": [True, False, False],
        "game_type": ["regular", "regular", "toc"],
        "round": ["Jeopardy", "Jeopardy", "Jeopardy"],
        "clue": ["a", "b", "c"],
        "answer": ["x", "y", "z"],
        "category": ["A", "B", "C"],
    })
    result = filter_scoreable(df)
    assert len(result) == 2
    assert set(result["clue"]) == {"b", "c"}


def test_score_clue_returns_difficulty_and_confidence():
    mock_client = MagicMock()
    mock_client.return_value = {"difficulty": 7, "confidence": 0.85}
    result = score_clue(mock_client, "some prompt text")
    assert result["difficulty"] == 7
    assert result["jev_confidence"] == 0.85


def test_score_clue_clamps_difficulty_range():
    mock_client = MagicMock()
    mock_client.return_value = {"difficulty": 15, "confidence": 0.5}
    result = score_clue(mock_client, "some prompt")
    assert 1 <= result["difficulty"] <= 10


# --- checkpoint recovery tests ---

def test_resume_retries_nan_difficulty(tmp_path):
    """NaN difficulty from parquet must not be treated as a successful score."""
    import numpy as np
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    hash_f = tmp_path / "jev_scores.prompt_hash"
    template = "Rate {category} / {clue} / {answer}"
    prompt_hash = hashlib.sha256(template.encode()).hexdigest()[:16]
    hash_f.write_text(prompt_hash)
    pd.DataFrame([
        {"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
         "difficulty": 5.0, "jev_confidence": 0.8},
        {"game_id": 1, "round": "Jeopardy", "row": 2.0, "column": 1.0,
         "difficulty": np.nan, "jev_confidence": np.nan},
    ]).to_parquet(ckpt)

    rows, done_keys, n_failed = _load_checkpoint(ckpt, hash_f, prompt_hash)

    assert len(rows) == 1, "NaN difficulty must not count as successful"
    assert n_failed == 1
    failed_key = _clue_key({"game_id": 1, "round": "Jeopardy", "row": 2.0, "column": 1.0})
    assert failed_key not in done_keys, "failed clue must be retryable"


def test_prompt_change_writes_new_hash(tmp_path):
    """After discarding a stale checkpoint, the new hash must be written immediately."""
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    hash_f = tmp_path / "jev_scores.prompt_hash"
    hash_f.write_text("aabbccdd00112233")
    pd.DataFrame([{"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
                   "difficulty": 5.0, "jev_confidence": 0.8}]).to_parquet(ckpt)

    new_template = "New prompt {category} {clue} {answer}"
    new_hash = hashlib.sha256(new_template.encode()).hexdigest()[:16]

    rows, done_keys, n_failed = _load_checkpoint(ckpt, hash_f, new_hash)

    assert not ckpt.exists(), "stale checkpoint must be deleted"
    assert hash_f.exists(), "new hash file must exist immediately after invalidation"
    assert hash_f.read_text().strip() == new_hash
    assert rows == []
    assert done_keys == set()


def test_checkpoint_kept_when_failures_remain(tmp_path):
    """Checkpoint must not be deleted when some clues exhausted retries."""
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    pd.DataFrame([{"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
                   "difficulty": 5.0, "jev_confidence": 0.8}]).to_parquet(ckpt)

    _cleanup_checkpoint(ckpt, n_failed=1)

    assert ckpt.exists(), "checkpoint must persist when failures remain so next run retries them"


def test_checkpoint_deleted_when_no_failures(tmp_path):
    """Checkpoint must be cleaned up when all clues scored successfully."""
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    pd.DataFrame([{"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
                   "difficulty": 5.0, "jev_confidence": 0.8}]).to_parquet(ckpt)

    _cleanup_checkpoint(ckpt, n_failed=0)

    assert not ckpt.exists(), "checkpoint must be removed when scoring completes cleanly"
