from django.test import Client, TestCase
from django.urls import reverse
from unittest.mock import patch


class SplashPageMetadataViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('panelsh_app.views.get_node_network_metadata')
    def test_returns_hostname_and_ip_addresses(self, get_node_network_metadata_mock):
        get_node_network_metadata_mock.return_value = {
            'hostname': 'panel-host',
            'ip_addresses': ['http://127.0.0.1'],
        }

        response = self.client.get(reverse('panelsh_app:splash_page_metadata'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            get_node_network_metadata_mock.return_value,
        )
