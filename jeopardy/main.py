"""Single CLI entry point for the jeopardy offline pipeline."""
import click


@click.group()
def cli():
    """Scrape j-archive and build the committed clues dataset."""


@cli.command()
def crawl():
    """Resumably fetch all games into data/games.jsonl (+ html_cache/)."""
    from jeopardy.crawl import run_crawl
    run_crawl()


@cli.command()
def build():
    """Build posts/jeopardy_ds/clues.parquet from data/games.jsonl."""
    from jeopardy.build_parquet import run_build
    run_build()


@cli.command(name="all")
def all_():
    """Run crawl, then build."""
    from jeopardy.crawl import run_crawl
    from jeopardy.build_parquet import run_build
    run_crawl()
    run_build()


@cli.command()
@click.option("--force", is_flag=True, help="Re-embed even if the cache exists.")
@click.option("--limit", default=None, type=int, help="Embed only the first N instances (for smoke tests).")
def embed(force, limit):
    """Build category documents and embed them (cached to data/)."""
    from jeopardy.analysis.embed import run_embed
    run_embed(force=force, limit=limit)


@cli.command()
@click.option("--k", default=None, type=int, help="Number of KMeans clusters (default from config).")
def cluster(k):
    """Cluster embeddings, project to 2D, and write cluster artifacts."""
    from jeopardy import config
    from jeopardy.analysis.cluster import run_cluster
    run_cluster(k if k is not None else config.DEFAULT_K)


@cli.command(name="name-clusters")
def name_clusters():
    """Optional: name clusters via OpenAI -> cluster_labels.csv (needs OPENAI_API_KEY)."""
    from jeopardy.analysis.name_clusters import run_name_clusters
    run_name_clusters()
