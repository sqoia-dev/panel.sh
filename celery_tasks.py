from datetime import timedelta
from os import getenv, path

import django
import sh
from celery import Celery
from tenacity import Retrying, stop_after_attempt, wait_fixed

try:
    django.setup()

    # Place imports that uses Django in this block.

    from lib import diagnostics
    from lib.utils import (
        connect_to_redis,
        is_balena_app,
        reboot_via_balena_supervisor,
        shutdown_via_balena_supervisor,
    )
    from panelsh_app.helpers import add_default_assets, remove_default_assets
except Exception:
    pass


__author__ = "Panelsh, Inc"
__copyright__ = "Copyright 2012-2024, Panelsh, Inc"
__license__ = "Dual License: GPLv2 and Commercial License"


CELERY_RESULT_BACKEND = getenv(
    'CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_BROKER_URL = getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_RESULT_EXPIRES = timedelta(hours=6)

r = connect_to_redis()
celery = Celery(
    'Panelsh Celery Worker',
    backend=CELERY_RESULT_BACKEND,
    broker=CELERY_BROKER_URL,
    result_expires=CELERY_TASK_RESULT_EXPIRES
)


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Calls cleanup() every hour.
    sender.add_periodic_task(3600, cleanup.s(), name='cleanup')
    sender.add_periodic_task(60*5, get_display_power.s(), name='display_power')


@celery.task(time_limit=30)
def get_display_power():
    r.set('display_power', diagnostics.get_display_power())
    r.expire('display_power', 3600)


@celery.task
def cleanup():
    sh.find(
        path.join(getenv('HOME'), 'panelsh_assets'),
        '-name', '*.tmp', '-delete')


@celery.task
def reboot_panelsh():
    """
    Background task to reboot Panelsh
    """
    if is_balena_app():
        for attempt in Retrying(
            stop=stop_after_attempt(5),
            wait=wait_fixed(1),
        ):
            with attempt:
                reboot_via_balena_supervisor()
    else:
        r.publish('hostcmd', 'reboot')


@celery.task
def shutdown_panelsh():
    """
    Background task to shutdown Panelsh
    """
    if is_balena_app():
        for attempt in Retrying(
            stop=stop_after_attempt(5),
            wait=wait_fixed(1),
        ):
            with attempt:
                shutdown_via_balena_supervisor()
    else:
        r.publish('hostcmd', 'shutdown')


@celery.task
def add_default_assets_task():
    """Background task to add default assets."""
    add_default_assets()


@celery.task
def remove_default_assets_task():
    """Background task to remove default assets."""
    remove_default_assets()
