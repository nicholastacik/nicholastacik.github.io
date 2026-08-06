"""KMeans clustering + UMAP 2D projection over category embeddings."""
import numpy as np
import pandas as pd

from jeopardy import config
from jeopardy.analysis.label import build_cluster_summary, write_naming_prompt


def cluster_embeddings(embeddings, k, seed):
    """KMeans → (labels, centers)."""
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(embeddings)
    return labels, km.cluster_centers_


def project_2d(embeddings, seed):
    """UMAP → (N, 2) coordinates, for visualization only."""
    import umap
    reducer = umap.UMAP(n_components=2, random_state=seed)
    return reducer.fit_transform(embeddings)


def centroid_distances(embeddings, labels):
    """Per-row Euclidean distance to the mean centroid of the row's own label."""
    labels = np.asarray(labels)
    dist = np.empty(len(labels), dtype=float)
    for lab in np.unique(labels):
        mask = labels == lab
        centroid = embeddings[mask].mean(axis=0)
        dist[mask] = np.linalg.norm(embeddings[mask] - centroid, axis=1)
    return dist


def run_cluster(k):
    instances = pd.read_parquet(config.INSTANCES_PATH)
    embeddings = np.load(config.EMBEDDINGS_PATH)
    labels, centers = cluster_embeddings(embeddings, k, config.RANDOM_SEED)
    coords = project_2d(embeddings, config.RANDOM_SEED)

    out = instances[["instance_id", "game_id", "round", "category"]].copy()
    out["cluster_id"] = labels
    out["umap_x"] = coords[:, 0]
    out["umap_y"] = coords[:, 1]
    out["centroid_dist"] = centroid_distances(embeddings, labels)
    config.CATEGORY_CLUSTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.CATEGORY_CLUSTERS_PATH, index=False)

    summary = build_cluster_summary(instances, embeddings, labels, centers)
    summary.to_parquet(config.CLUSTER_SUMMARY_PATH, index=False)
    write_naming_prompt(summary, config.NAMING_PROMPT_PATH)
    print(f"Clustered {len(out):,} instances into {k} clusters -> {config.CATEGORY_CLUSTERS_PATH}")


def run_cluster_dist():
    clusters = pd.read_parquet(config.CATEGORY_CLUSTERS_PATH)
    embeddings = np.load(config.EMBEDDINGS_PATH)
    if len(embeddings) != len(clusters):
        raise SystemExit(
            f"embeddings ({len(embeddings)}) and clusters ({len(clusters)}) row counts differ; "
            "re-run `jeopardy embed` + `jeopardy cluster` first"
        )
    clusters["centroid_dist"] = centroid_distances(embeddings, clusters["cluster_id"].to_numpy())
    clusters.to_parquet(config.CATEGORY_CLUSTERS_PATH, index=False)
    print(f"Added centroid_dist to {len(clusters):,} rows -> {config.CATEGORY_CLUSTERS_PATH}")
