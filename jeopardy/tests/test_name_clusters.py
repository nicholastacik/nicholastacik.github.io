import pandas as pd
from jeopardy.analysis import name_clusters as nc


def test_parse_response():
    assert nc.parse_response('{"0": "U.S. Presidents", "1": "Pasta"}') == {0: "U.S. Presidents", 1: "Pasta"}


def test_write_labels_sorted(tmp_path):
    p = tmp_path / "labels.csv"
    nc.write_labels({1: "Beta", 0: "Alpha"}, p)
    lines = p.read_text().splitlines()
    assert lines[0] == "cluster_id,name"
    assert lines[1] == "-1,Misc: Hard to Classify"  # overflow type preserved, sorts first
    assert lines[2] == "0,Alpha"
    assert lines[3] == "1,Beta"


def test_write_labels_preserves_misc_when_absent(tmp_path):
    import csv as _csv
    p = tmp_path / "labels.csv"
    nc.write_labels({0: "Alpha"}, p)  # names lacks -1; a re-naming run must not drop the misc type
    rows = {int(r["cluster_id"]): r["name"] for r in _csv.DictReader(open(p))}
    assert rows[nc.config.MISC_ID] == nc.config.MISC_LABEL


def test_build_prompt_includes_fingerprints():
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 10,
        "top_category_names": ["PASTA (5)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    prompt = nc.build_prompt(summary)
    assert "Cluster 0" in prompt and "PASTA" in prompt and "penne" in prompt


def test_run_name_clusters_stubbed(tmp_path, monkeypatch):
    summary = pd.DataFrame([{
        "cluster_id": 0, "size": 5,
        "top_category_names": ["PASTA (5)"], "top_terms": ["penne"], "exemplars": ["PASTA"],
    }])
    summary.to_parquet(tmp_path / "summary.parquet")
    monkeypatch.setattr(nc.config, "CLUSTER_SUMMARY_PATH", tmp_path / "summary.parquet")
    monkeypatch.setattr(nc.config, "CLUSTER_LABELS_PATH", tmp_path / "labels.csv")
    monkeypatch.setattr(nc, "_complete", lambda prompt: '{"0": "Pasta"}')
    nc.run_name_clusters()
    lines = (tmp_path / "labels.csv").read_text().splitlines()
    assert "0,Pasta" in lines
    assert "-1,Misc: Hard to Classify" in lines
