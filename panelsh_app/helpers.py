import logging
import uuid
from os import getenv, path

import yaml
from django.shortcuts import render
from django.utils import timezone

from lib.github import is_up_to_date
from lib.utils import get_video_duration
from settings import settings
from panelsh_app.models import Asset


logger = logging.getLogger(__name__)


def template(request, template_name, context):
    """
    This is a helper function that is used to render a template
    with some global context. This is used to avoid having to
    repeat code in other views.
    """

    context['date_format'] = settings['date_format']
    context['default_duration'] = settings['default_duration']
    context['default_streaming_duration'] = (
        settings['default_streaming_duration']
    )
    context['template_settings'] = {
        'imports': ['from lib.utils import template_handle_unicode'],
        'default_filters': ['template_handle_unicode'],
    }
    context['up_to_date'] = is_up_to_date()
    context['use_24_hour_clock'] = settings['use_24_hour_clock']

    return render(request, template_name, context)


def prepare_default_asset(**kwargs):
    if kwargs['mimetype'] not in ['image', 'video', 'webpage']:
        return

    asset_id = 'default_{}'.format(uuid.uuid4().hex)
    duration = (
        int(get_video_duration(kwargs['uri']).total_seconds())
        if "video" == kwargs['mimetype']
        else kwargs['duration']
    )

    return {
        'asset_id': asset_id,
        'duration': duration,
        'end_date': kwargs['end_date'],
        'is_enabled': True,
        'is_processing': 0,
        'mimetype': kwargs['mimetype'],
        'name': kwargs['name'],
        'nocache': 0,
        'play_order': 0,
        'skip_asset_check': 0,
        'start_date': kwargs['start_date'],
        'uri': kwargs['uri']
    }


def add_default_assets():
    settings.load()

    datetime_now = timezone.now()
    default_asset_settings = {
        'start_date': datetime_now,
        'end_date': datetime_now.replace(year=datetime_now.year + 6),
        'duration': settings['default_duration']
    }

    default_assets_yaml = path.join(
        getenv('HOME'),
        '.panelsh/default_assets.yml',
    )

    with open(default_assets_yaml, 'r') as yaml_file:
        try:
            default_assets = (yaml.safe_load(yaml_file) or {}).get('assets', [])
        except yaml.YAMLError as exc:
            logger.error("Failed to parse default assets YAML: %s", exc)
            return

        if not isinstance(default_assets, list):
            logger.error(
                "Default assets YAML 'assets' key must be a list, got %s",
                type(default_assets).__name__,
            )
            return

        required_fields = ['name', 'uri', 'mimetype']

        for default_asset in default_assets:
            if not isinstance(default_asset, dict):
                logger.error("Default asset entry must be a mapping: %s", default_asset)
                continue

            missing_fields = [
                field for field in required_fields if not default_asset.get(field)
            ]
            if missing_fields:
                logger.error(
                    "Default asset missing required field(s) %s: %s",
                    ', '.join(missing_fields),
                    default_asset,
                )
                continue

            default_asset_settings.update({
                'name': default_asset.get('name'),
                'uri': default_asset.get('uri'),
                'mimetype': default_asset.get('mimetype'),
            })
            asset = prepare_default_asset(**default_asset_settings)

            if asset:
                Asset.objects.create(**asset)
            else:
                logger.error(
                    "Default asset failed validation or had unsupported mimetype: %s",
                    default_asset,
                )


def remove_default_assets():
    settings.load()

    for asset in Asset.objects.all():
        if asset.asset_id.startswith('default_'):
            asset.delete()
