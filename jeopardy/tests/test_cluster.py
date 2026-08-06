import numpy as np
from jeopardy.analysis.cluster import cluster_embeddings, project_2d, centroid_distances


def test_centroid_distances_measures_to_own_cluster_not_nearest():
    # Two tight clusters far apart on axis 0. Row 2 is labeled 0 but sits at
    # the cluster-1 location, so its distance must be large (to cluster 0's
    # centroid), proving we measure to the ASSIGNED centroid, not the nearest.
    emb = np.array([
        [0.0, 0.0],   # label 0, at cluster-0 centroid
        [0.0, 0.0],   # label 0
        [10.0, 0.0],  # label 0 but physically among cluster 1
        [10.0, 0.0],  # label 1
        [10.0, 0.0],  # label 1
    ])
    labels = np.array([0, 0, 0, 1, 1])
    d = centroid_distances(emb, labels)
    assert d.shape == (5,)
    # cluster-0 centroid = mean of rows 0,1,2 = (3.33, 0); cluster-1 centroid = (10,0)
    assert d[3] == 0.0 and d[4] == 0.0          # exactly at cluster-1 centroid
    assert d[2] > d[0]                           # the misfit row is farther out
    assert d[2] > 6.0                            # ~6.67 from cluster-0 centroid


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
