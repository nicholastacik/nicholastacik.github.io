"""Overflow 'hard to classify' pool: worst-fitting categories by centroid distance."""


def misc_membership(clusters_df, fraction, misc_id):
    n = max(1, round(len(clusters_df) * fraction))
    worst = clusters_df.nlargest(n, "centroid_dist")
    out = worst[["game_id", "round", "category"]].copy()
    out["cluster_id"] = misc_id
    return out.reset_index(drop=True)
