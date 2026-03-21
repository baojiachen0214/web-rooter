import os
import unittest
from unittest import mock

from core.http_ssl import build_client_ssl_context


class HttpSslContextTests(unittest.TestCase):
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
        sentinel = object()
        certifi_module.where.return_value = "/tmp/certifi-ca.pem"
        create_default_context.return_value = sentinel

        result = build_client_ssl_context()

        self.assertIs(result, sentinel)
        create_default_context.assert_called_once_with(cafile="/tmp/certifi-ca.pem")

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
