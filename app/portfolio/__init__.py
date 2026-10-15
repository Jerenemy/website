import click
from flask import current_app, g
from flask.cli import with_appcontext

from .store import PortfolioStore


def get_portfolio_store() -> PortfolioStore:
    if "portfolio_store" not in g:
        g.portfolio_store = PortfolioStore(current_app.config["PORTFOLIO_DATA_PATH"],
                                           current_app.config["PORTFOLIO_SEED_PATH"])
    return g.portfolio_store


@click.command("portfolio-copy")
@click.option("--dry-run", is_flag=True, help="List what would change without writing.")
@with_appcontext
def copy_command(dry_run: bool) -> None:
    """Bring the works' words from the repository's seed into the live portfolio."""
    changed = get_portfolio_store().import_copy(current_app.config["PORTFOLIO_SEED_PATH"], dry_run=dry_run)
    for item_id, field in changed:
        click.echo(f"{item_id}.{field}")
    click.echo(f"{len(changed)} field(s) {'would change' if dry_run else 'updated'}.")
