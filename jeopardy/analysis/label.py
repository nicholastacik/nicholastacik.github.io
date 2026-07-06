"""Three-part deterministic fingerprints for clusters + a naming prompt."""
from collections import Counter

import numpy as np
import pandas as pd


def top_category_names(categories, n=10):
    return [f"{name} ({count})" for name, count in Counter(categories).most_common(n)]


def ctfidf_terms(cluster_docs, n=10):
    """Per-cluster distinctive terms: TF-IDF over one concatenated doc per cluster."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(
        stop_words="english", max_features=5000,
        token_pattern=r"[A-Za-z][A-Za-z'\-]+",
    )
    matrix = vec.fit_transform(cluster_docs)
    terms = np.array(vec.get_feature_names_out())
    out = []
    for i in range(matrix.shape[0]):
        row = matrix.getrow(i).toarray().ravel()
        top = row.argsort()[::-1][:n]
        out.append([terms[j] for j in top if row[j] > 0])
    return out


def nearest_exemplars(embeddings, centroid, cluster_idx, categories, n=5):
    """Category names of the `n` instances nearest the cluster centroid."""
    distances = np.linalg.norm(embeddings[cluster_idx] - centroid, axis=1)
    order = np.argsort(distances)[:n]
    return [categories[cluster_idx[j]] for j in order]


def build_cluster_summary(instances, embeddings, labels, centers):
    categories = instances["category"].to_numpy()
    documents = instances["document"].to_numpy()
    k = centers.shape[0]
    cluster_docs = [" ".join(documents[np.where(labels == cid)[0]]) for cid in range(k)]
    terms = ctfidf_terms(cluster_docs)
    rows = []
    for cid in range(k):
        idx = np.where(labels == cid)[0]
        rows.append({
            "cluster_id": cid,
            "size": int(len(idx)),
            "top_category_names": top_category_names(categories[idx].tolist()),
            "top_terms": terms[cid],
            "exemplars": nearest_exemplars(embeddings, centers[cid], idx, categories),
        })
    return pd.DataFrame(rows).sort_values("size", ascending=False).reset_index(drop=True)


def write_naming_prompt(summary, path):
    lines = [
        "# Cluster naming prompt",
        "",
        "For each cluster, reply with JSON mapping the cluster id (as a string key) to a",
        "short 2-4 word human-readable category-type name, e.g. {\"0\": \"U.S. Presidents\"}.",
        "",
    ]
    for _, r in summary.iterrows():
        lines.append(f"## Cluster {r['cluster_id']} (size {r['size']})")
        lines.append(f"- Top categories: {', '.join(r['top_category_names'])}")
        lines.append(f"- Distinctive terms: {', '.join(r['top_terms'])}")
        lines.append(f"- Exemplars: {', '.join(r['exemplars'])}")
        lines.append("")
    path.write_text("\n".join(lines))
