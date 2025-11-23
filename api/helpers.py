import json
from datetime import datetime, timezone as dt_timezone

from dateutil import parser as date_parser
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from panelsh_app.models import Asset


class AssetCreationError(Exception):
    def __init__(self, errors):
        self.errors = errors


def parse_timezone_aware_datetime(value):
    """Return a timezone-aware datetime in UTC.

    Accepts ISO 8601 strings or ``datetime`` instances and ensures the
    resulting object is aware and normalized to UTC. Empty values are
    returned unchanged to allow optional fields to propagate naturally.
    """

    if value in [None, ""]:
        return value

    if isinstance(value, str):
        try:
            parsed_value = date_parser.isoparse(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid datetime value: {value}") from exc
    elif isinstance(value, datetime):
        parsed_value = value
    else:
        raise TypeError(
            "Datetime values must be ISO-formatted strings or datetime instances."
        )

    if timezone.is_naive(parsed_value):
        parsed_value = timezone.make_aware(parsed_value, dt_timezone.utc)

    return parsed_value.astimezone(dt_timezone.utc)


def update_asset(asset, data):
    for key, value in list(data.items()):

        if (
            key in ['asset_id', 'is_processing', 'mimetype', 'uri']
            or key not in asset
        ):
            continue

        if key in ['start_date', 'end_date']:
            value = parse_timezone_aware_datetime(value)

        if (
            key in [
                'play_order',
                'skip_asset_check',
                'is_enabled',
                'is_active',
                'nocache',
            ]
        ):
            value = int(value)

        if key == 'duration':
            if "video" not in asset['mimetype']:
                continue
            value = int(value)

        asset.update({key: value})


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        return response

    return Response(
        {"error": str(exc)},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def get_active_asset_ids():
    enabled_assets = Asset.objects.filter(
        is_enabled=1,
        start_date__isnull=False,
        end_date__isnull=False,
    )
    return [
        asset.asset_id
        for asset in enabled_assets
        if asset.is_active()
    ]


def save_active_assets_ordering(active_asset_ids):
    for i, asset_id in enumerate(active_asset_ids):
        Asset.objects.filter(asset_id=asset_id).update(play_order=i)


def parse_request(request):
    # For backward compatibility
    raw_data = request.data

    try:
        return json.loads(raw_data)
    except (TypeError, ValueError):
        pass

    if not isinstance(raw_data, dict):
        raise ValueError(
            "Request data is not valid JSON and does not include a 'model' field."
        )

    if 'model' not in raw_data:
        raise ValueError("Request data is missing the required 'model' field.")

    try:
        return json.loads(raw_data['model'])
    except (TypeError, ValueError) as exc:
        raise ValueError("Request 'model' field is not valid JSON.") from exc
