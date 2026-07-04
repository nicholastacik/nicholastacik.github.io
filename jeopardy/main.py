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
