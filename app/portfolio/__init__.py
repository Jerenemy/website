from flask import current_app, g

from .store import PortfolioStore


def get_portfolio_store() -> PortfolioStore:
    if "portfolio_store" not in g:
        g.portfolio_store = PortfolioStore(current_app.config["PORTFOLIO_DATA_PATH"])
    return g.portfolio_store
