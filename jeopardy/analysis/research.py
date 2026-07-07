"""Generate the interactive research tool (type -> entities -> live Wikipedia facts)."""
import pandas as pd


def build_research_data(tokens_df, labels):
    """Per-type entity data for the research page, sorted by applicability desc."""
    out = []
    for cluster_id, name in labels.items():
        rows = tokens_df[tokens_df["cluster_id"] == cluster_id]
        applicability = int(rows["n_qualifying_phrases"].iloc[0]) if len(rows) else 0
        entities = [
            {"phrase": r["phrase"], "count": int(r["count"])}
            for _, r in rows.iterrows()
            if r["phrase"] is not None and pd.notna(r["phrase"])
        ]
        out.append({
            "cluster_id": int(cluster_id),
            "name": name,
            "applicability": applicability,
            "entities": entities,
        })
    out.sort(key=lambda d: d["applicability"], reverse=True)
    return out
