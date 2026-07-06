import numpy as np
from jeopardy.analysis.cluster import cluster_embeddings, project_2d


def test_cluster_embeddings_shape_and_separation():
    rng = np.random.default_rng(0)
    emb = np.vstack([
        rng.normal(0, 0.05, (20, 8)) + 5.0,
        rng.normal(0, 0.05, (20, 8)),
    ])
    labels, centers = cluster_embeddings(emb, k=2, seed=42)
    assert labels.shape == (40,)
    assert centers.shape == (2, 8)
    # the two blobs land in different clusters
    assert labels[0] != labels[-1]


def test_project_2d_shape():
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(30, 8))
    coords = project_2d(emb, seed=42)
    assert coords.shape == (30, 2)
