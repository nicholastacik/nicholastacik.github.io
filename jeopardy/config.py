"""Shared paths and constants for the jeopardy offline pipeline."""
from pathlib import Path

BASE_URL = "https://www.j-archive.com"
USER_AGENT = "jeopardy-ds-research (personal research; contact nick@gray-os.com)"

# Politeness: seconds to sleep between *network* fetches (not cache hits).
MIN_DELAY = 1.0
MAX_DELAY = 1.5

# Clue dollar values doubled on this air date; used to derive board values.
VALUE_DOUBLING_DATE = "2001-11-26"

PKG_DIR = Path(__file__).resolve().parent          # .../jeopardy
REPO_ROOT = PKG_DIR.parent                          # repo root
DATA_DIR = PKG_DIR / "data"
HTML_CACHE = DATA_DIR / "html_cache"
JSONL_PATH = DATA_DIR / "games.jsonl"
PARQUET_PATH = REPO_ROOT / "posts" / "jeopardy_ds" / "clues.parquet"

# --- analysis: category clustering ---
EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 512-token window, 384-dim
RANDOM_SEED = 42                          # shuffle + KMeans + UMAP
DEFAULT_K = 50                            # KMeans clusters
OPENAI_MODEL = "gpt-4o-mini"              # optional cluster naming

EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"       # gitignored cache
INSTANCES_PATH = DATA_DIR / "instances.parquet"     # gitignored instance index
_POST_DIR = REPO_ROOT / "posts" / "jeopardy_ds"
CATEGORY_CLUSTERS_PATH = _POST_DIR / "category_clusters.parquet"
CLUSTER_SUMMARY_PATH = _POST_DIR / "cluster_summary.parquet"
NAMING_PROMPT_PATH = _POST_DIR / "cluster_naming_prompt.md"
CLUSTER_LABELS_PATH = _POST_DIR / "cluster_labels.csv"
CATEGORY_TOKENS_PATH = _POST_DIR / "category_tokens.parquet"
RESEARCH_HTML_PATH = _POST_DIR / "research" / "index.html"
