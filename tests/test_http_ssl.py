import os
import ssl
import unittest
from unittest import mock

from core.http_ssl import build_client_ssl_context, is_insecure_ssl_enabled


class HttpSslContextTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"WEB_ROOTER_INSECURE_SSL": "1"}, clear=True)
    @mock.patch("core.http_ssl.ssl.create_default_context")
    def test_allows_explicit_insecure_ssl_override(self, create_default_context: mock.Mock) -> None:
        context = mock.Mock()
        create_default_context.return_value = context

        result = build_client_ssl_context()

        self.assertTrue(is_insecure_ssl_enabled())
        self.assertIs(result, context)
        create_default_context.assert_called_once_with()
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)

    @mock.patch.dict(os.environ, {"WEB_ROOTER_SSL_CA_FILE": "/tmp/custom-ca.pem"}, clear=True)
    @mock.patch("core.http_ssl.ssl.create_default_context")
    def test_prefers_explicit_ca_file_from_env(self, create_default_context: mock.Mock) -> None:
        sentinel = object()
        create_default_context.return_value = sentinel

        result = build_client_ssl_context()

        self.assertIs(result, sentinel)
        create_default_context.assert_called_once_with(cafile="/tmp/custom-ca.pem")

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("core.http_ssl.ssl.create_default_context")
    @mock.patch("core.http_ssl.certifi")
    def test_uses_certifi_bundle_when_available(
        self,
        certifi_module: mock.Mock,
        create_default_context: mock.Mock,
    ) -> None:
        certifi_module.where.return_value = "/tmp/certifi-ca.pem"
        context = mock.Mock()
        create_default_context.return_value = context

        result = build_client_ssl_context()

        self.assertIs(result, context)
        create_default_context.assert_called_once_with()
        context.load_verify_locations.assert_called_once_with(cafile="/tmp/certifi-ca.pem")

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("core.http_ssl.ssl.create_default_context")
    @mock.patch("core.http_ssl.certifi", None)
    def test_falls_back_to_system_store_when_certifi_missing(
        self,
        create_default_context: mock.Mock,
    ) -> None:
        sentinel = object()
        create_default_context.return_value = sentinel

        result = build_client_ssl_context()

        self.assertIs(result, sentinel)
        create_default_context.assert_called_once_with()

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch("core.http_ssl.ssl.create_default_context")
    @mock.patch("core.http_ssl.certifi")
    def test_keeps_system_store_when_certifi_load_fails(
        self,
        certifi_module: mock.Mock,
        create_default_context: mock.Mock,
    ) -> None:
        context = mock.Mock()
        context.load_verify_locations.side_effect = OSError("bad cert bundle")
        certifi_module.where.return_value = "/tmp/certifi-ca.pem"
        create_default_context.return_value = context

        result = build_client_ssl_context()

        self.assertIs(result, context)
        create_default_context.assert_called_once_with()
        context.load_verify_locations.assert_called_once_with(cafile="/tmp/certifi-ca.pem")
