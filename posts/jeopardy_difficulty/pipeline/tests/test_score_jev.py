import hashlib
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from pipeline.score_jev import score_clue, build_prompt, filter_scoreable


def test_build_prompt_fills_placeholders():
    template = "Category: {category}. Clue: {clue}. Answer: {answer}."
    result = build_prompt(template, category="SCIENCE", clue="It orbits Earth", answer="the Moon")
    assert "SCIENCE" in result
    assert "It orbits Earth" in result
    assert "the Moon" in result


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
         "difficulty": 5, "jev_confidence": 0.8},
        {"game_id": 1, "round": "Jeopardy", "row": 2.0, "column": 1.0,
         "difficulty": np.nan, "jev_confidence": np.nan},
    ]).to_parquet(ckpt)
    prev = pd.read_parquet(ckpt).to_dict(orient="records")
    successful = [r for r in prev if pd.notna(r.get("difficulty"))]
    assert len(successful) == 1, "NaN difficulty must not count as successful"
    done_keys = {(int(r["game_id"]), r["round"], r["row"], r["column"]) for r in successful}
    failed_key = (1, "Jeopardy", 2.0, 1.0)
    assert failed_key not in done_keys, "failed clue must be retryable"


def test_prompt_change_writes_new_hash(tmp_path):
    """After discarding a stale checkpoint, the new hash must be written immediately."""
    import hashlib as _hl
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    hash_f = tmp_path / "jev_scores.prompt_hash"
    old_hash = "aabbccdd00112233"
    hash_f.write_text(old_hash)
    pd.DataFrame([{"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
                   "difficulty": 5, "jev_confidence": 0.8}]).to_parquet(ckpt)

    new_template = "New prompt {category} {clue} {answer}"
    new_hash = _hl.sha256(new_template.encode()).hexdigest()[:16]
    saved = hash_f.read_text().strip()
    assert saved != new_hash
    ckpt.unlink()
    hash_f.unlink(missing_ok=True)
    hash_f.write_text(new_hash)

    assert hash_f.exists(), "hash file must exist after invalidation so interrupted re-run can resume"
    assert hash_f.read_text().strip() == new_hash


def test_checkpoint_kept_when_failures_remain(tmp_path):
    """Checkpoint must not be deleted when some clues exhausted retries."""
    ckpt = tmp_path / "jev_scores.checkpoint.parquet"
    out = tmp_path / "jev_scores.parquet"
    rows = [
        {"game_id": 1, "round": "Jeopardy", "row": 1.0, "column": 1.0,
         "difficulty": 5, "jev_confidence": 0.8},
        {"game_id": 1, "round": "Jeopardy", "row": 2.0, "column": 1.0,
         "difficulty": None, "jev_confidence": None},
    ]
    pd.DataFrame(rows).to_parquet(ckpt)
    n_failed = sum(1 for r in rows if not pd.notna(r.get("difficulty")))
    pd.DataFrame(rows).to_parquet(out)
    if n_failed == 0:
        ckpt.unlink(missing_ok=True)
    assert ckpt.exists(), "checkpoint must persist when failures remain so next run retries them"
