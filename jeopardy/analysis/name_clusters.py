"""Optional: name clusters via the OpenAI API -> committed cluster_labels.csv."""
import csv
import json

import pandas as pd

from jeopardy import config


def build_prompt(summary):
    lines = [
        "You are naming clusters of Jeopardy categories. For each cluster below, reply",
        "with a JSON object mapping the cluster id (string key) to a short 2-4 word",
        'category-type name, e.g. {"0": "U.S. Presidents"}. Reply with JSON only.',
        "",
    ]
    for _, r in summary.iterrows():
        lines.append(f"Cluster {r['cluster_id']} (size {r['size']})")
        lines.append(f"  top categories: {', '.join(r['top_category_names'])}")
        lines.append(f"  distinctive terms: {', '.join(r['top_terms'])}")
        lines.append(f"  exemplars: {', '.join(r['exemplars'])}")
        lines.append("")
    return "\n".join(lines)


def parse_response(text):
    return {int(k): str(v) for k, v in json.loads(text).items()}


def write_labels(names, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["cluster_id", "name"])
        for cid in sorted(names):
            writer.writerow([cid, names[cid]])


def _complete(prompt):
    """Send the prompt to OpenAI and return the raw text reply."""
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY from the environment
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def run_name_clusters():
    summary = pd.read_parquet(config.CLUSTER_SUMMARY_PATH)
    names = parse_response(_complete(build_prompt(summary)))
    write_labels(names, config.CLUSTER_LABELS_PATH)
    print(f"Wrote {len(names)} cluster names -> {config.CLUSTER_LABELS_PATH}")
