import numpy as np
import pandas as pd
from jeopardy.analysis import embed as embed_mod


class FakeModel:
    def __init__(self):
        self.calls = 0

    def encode(self, docs, **kwargs):
        self.calls += 1
        return np.ones((len(list(docs)), 4), dtype="float32")


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(embed_mod.config, "PARQUET_PATH", tmp_path / "clues.parquet")
    monkeypatch.setattr(embed_mod.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embed_mod.config, "EMBEDDINGS_PATH", tmp_path / "embeddings.npy")
    monkeypatch.setattr(embed_mod.config, "INSTANCES_PATH", tmp_path / "instances.parquet")
    pd.DataFrame([
        {"game_id": 1, "round": "Final", "category": "X", "clue": "c", "answer": "a"},
        {"game_id": 2, "round": "Final", "category": "Y", "clue": "d", "answer": "b"},
    ]).to_parquet(tmp_path / "clues.parquet")


def test_run_embed_writes_cache(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fake = FakeModel()
    monkeypatch.setattr(embed_mod, "get_model", lambda: fake)
    embed_mod.run_embed()
    assert (tmp_path / "embeddings.npy").exists()
    assert (tmp_path / "instances.parquet").exists()
    assert fake.calls == 1
    assert np.load(tmp_path / "embeddings.npy").shape[0] == 2


def test_run_embed_cache_skips_encode(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    (tmp_path / "embeddings.npy").write_bytes(b"x")
    (tmp_path / "instances.parquet").write_bytes(b"x")

    def boom():
        raise AssertionError("get_model called on a cache hit")

    monkeypatch.setattr(embed_mod, "get_model", boom)
    embed_mod.run_embed()  # should return early, not encode


def test_run_embed_limit(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fake = FakeModel()
    monkeypatch.setattr(embed_mod, "get_model", lambda: fake)
    embed_mod.run_embed(limit=1)
    assert np.load(tmp_path / "embeddings.npy").shape[0] == 1
