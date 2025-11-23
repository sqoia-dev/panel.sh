import hashlib
from unittest import TestCase

from lib.auth import update_basic_auth_credentials


class UpdateBasicAuthCredentialsTest(TestCase):
    def setUp(self):
        self.settings = {'user': '', 'password': ''}

    def test_requires_username_when_setting_credentials(self):
        with self.assertRaises(ValueError):
            update_basic_auth_credentials(self.settings, '', 'pass', 'pass', None)

    def test_requires_password_when_setting_username(self):
        with self.assertRaises(ValueError):
            update_basic_auth_credentials(self.settings, 'new_user', '', '', None)

    def test_sets_initial_username_and_password(self):
        update_basic_auth_credentials(
            self.settings, 'new_user', 'pass', 'pass', None
        )

        self.assertEqual(self.settings['user'], 'new_user')
        self.assertEqual(
            self.settings['password'],
            hashlib.sha256('pass'.encode('utf-8')).hexdigest(),
        )

    def test_changing_username_requires_current_password(self):
        self.settings.update({
            'user': 'existing',
            'password': hashlib.sha256('current'.encode('utf-8')).hexdigest(),
        })

        with self.assertRaises(ValueError):
            update_basic_auth_credentials(
                self.settings, 'new_user', '', '', None
            )

    def test_change_username_with_correct_password(self):
        self.settings.update({
            'user': 'existing',
            'password': hashlib.sha256('current'.encode('utf-8')).hexdigest(),
        })

        update_basic_auth_credentials(
            self.settings, 'new_user', '', '', True
        )

        self.assertEqual(self.settings['user'], 'new_user')

    def test_changing_password_requires_current_password(self):
        self.settings.update({
            'user': 'existing',
            'password': hashlib.sha256('current'.encode('utf-8')).hexdigest(),
        })

        with self.assertRaises(ValueError):
            update_basic_auth_credentials(
                self.settings, 'existing', 'new', 'new', None
            )

    def test_change_password_with_matching_confirmation(self):
        self.settings.update({
            'user': 'existing',
            'password': hashlib.sha256('current'.encode('utf-8')).hexdigest(),
        })

        update_basic_auth_credentials(
            self.settings, 'existing', 'new', 'new', True
        )

        self.assertEqual(
            self.settings['password'],
            hashlib.sha256('new'.encode('utf-8')).hexdigest(),
        )

    def test_new_passwords_must_match(self):
        self.settings.update({
            'user': 'existing',
            'password': hashlib.sha256('current'.encode('utf-8')).hexdigest(),
        })

        with self.assertRaises(ValueError):
            update_basic_auth_credentials(
                self.settings, 'existing', 'new', 'different', True
            )
