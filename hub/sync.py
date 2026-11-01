import os
from .delta_sync import deliver


def sync(store, config):
    return deliver(store,config['origin'],os.environ.get('HUB_SYNC_TOKEN'),os.environ.get('HUB_SITE_ACCESS_TOKEN'))
