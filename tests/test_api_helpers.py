import sys
import types
import unittest

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[],
        TIME_ZONE="UTC",
        USE_TZ=True,
        SECRET_KEY="test-key",
        REST_FRAMEWORK={},
    )

sys.modules.setdefault("panelsh_app", types.ModuleType("panelsh_app"))
sys.modules["panelsh_app"].models = types.ModuleType("panelsh_app.models")
sys.modules["panelsh_app.models"] = sys.modules["panelsh_app"].models
sys.modules["panelsh_app.models"].Asset = object

django.setup()

from api.helpers import parse_request


class DummyRequest:
    def __init__(self, data):
        self.data = data


class ParseRequestTestCase(unittest.TestCase):
    def test_parses_direct_json_string(self):
        request = DummyRequest('{"foo": "bar"}')

        self.assertEqual(parse_request(request), {"foo": "bar"})

    def test_parses_json_from_model_field(self):
        request = DummyRequest({"model": '{"foo": "bar"}'})

        self.assertEqual(parse_request(request), {"foo": "bar"})

    def test_raises_clear_error_when_model_missing(self):
        request = DummyRequest({"foo": "bar"})

        with self.assertRaisesRegex(
            ValueError, "missing the required 'model' field"
        ):
            parse_request(request)
