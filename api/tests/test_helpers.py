"""Tests for helper utilities used across the API."""

from datetime import datetime, timedelta, timezone as dt_timezone

import django
import pytest
from django.conf import settings as django_settings

if not django_settings.configured:
    django_settings.configure(
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'panelsh_app',
        ],
        TIME_ZONE='UTC',
        USE_TZ=True,
        SECRET_KEY='test',
        REST_FRAMEWORK={},
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
    )
    django.setup()

from api.helpers import parse_timezone_aware_datetime


def test_parse_timezone_aware_datetime_from_string_normalizes_to_utc():
    parsed = parse_timezone_aware_datetime("2019-08-24T14:15:22Z")

    assert parsed.year == 2019
    assert parsed.month == 8
    assert parsed.day == 24
    assert parsed.utcoffset() == timedelta(0)
    assert parsed.tzinfo == dt_timezone.utc


def test_parse_timezone_aware_datetime_from_naive_datetime():
    naive = datetime(2019, 8, 24, 14, 15, 22)

    parsed = parse_timezone_aware_datetime(naive)

    assert parsed.tzinfo == dt_timezone.utc
    assert parsed.utcoffset() == timedelta(0)


def test_parse_timezone_aware_datetime_rejects_invalid_type():
    with pytest.raises(TypeError):
        parse_timezone_aware_datetime(123)
