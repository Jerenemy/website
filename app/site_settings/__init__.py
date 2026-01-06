from flask import current_app, g

from .store import SiteSettingsStore


def get_site_settings_store() -> SiteSettingsStore:
    if "site_settings_store" not in g:
        g.site_settings_store = SiteSettingsStore(current_app.config["SITE_SETTINGS_PATH"])
    return g.site_settings_store
