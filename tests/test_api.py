"""Tests for the FluxCD Kubernetes API client error handling."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load the real api module with enough stubs for it to import
# ---------------------------------------------------------------------------

_pkg_dir = Path(__file__).parent.parent / "custom_components" / "fluxcd_k8s"

# Pull the ApiException stub that conftest registered
_k8s_exc = sys.modules["kubernetes_asyncio.client.exceptions"]
ApiException = _k8s_exc.ApiException


def _ensure_k8s_client_attrs():
    """Add required attributes to the kubernetes_asyncio.client stub."""
    import types as _types

    k8s_client = sys.modules["kubernetes_asyncio.client"]
    if not hasattr(k8s_client, "ApiClient"):
        k8s_client.ApiClient = object
    if not hasattr(k8s_client, "CustomObjectsApi"):
        k8s_client.CustomObjectsApi = object
    if not hasattr(k8s_client, "VersionApi"):
        k8s_client.VersionApi = object
    if not hasattr(k8s_client, "Configuration"):
        k8s_client.Configuration = object

    k8s = sys.modules["kubernetes_asyncio"]
    if not hasattr(k8s, "client"):
        k8s.client = k8s_client
    k8s_config = sys.modules.get("kubernetes_asyncio.config")
    if k8s_config is None:
        k8s_config = _types.ModuleType("kubernetes_asyncio.config")
        sys.modules["kubernetes_asyncio.config"] = k8s_config
    if not hasattr(k8s, "config"):
        k8s.config = k8s_config


def _load_api_module():
    """Load the real api.py module, reusing existing stubs."""
    _ensure_k8s_client_attrs()

    full_name = "fluxcd_k8s._real_api"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(full_name, _pkg_dir / "api.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "fluxcd_k8s"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_api_module = _load_api_module()
FluxKubernetesClient = _api_module.FluxKubernetesClient

# Imported by api.py via a relative import, so it is already in sys.modules.
_kubeconfig_module = sys.modules["fluxcd_k8s.kubeconfig"]
KubeconfigNotFound = _kubeconfig_module.KubeconfigNotFound


@pytest.fixture(autouse=True)
def _isolate_kubeconfig_search(monkeypatch):
    """Stop discovery from reaching a kubeconfig on the machine running tests.

    DEFAULT_SEARCH_DIRS points at /config and /root, which do exist on the
    systems this integration targets.
    """
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(_kubeconfig_module, "DEFAULT_SEARCH_DIRS", ())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNotFoundHandling:
    """Verify that 404 ApiException is handled silently at DEBUG level."""

    @pytest.mark.asyncio
    async def test_404_does_not_emit_warning(self, caplog):
        """A 404 ApiException should be logged at DEBUG, not WARNING."""
        flux_client = FluxKubernetesClient(hass=MagicMock(), access_mode="kubeconfig")
        flux_client._api_client = object()

        with (
            patch.object(_api_module, "CustomObjectsApi", return_value=MagicMock()),
            patch.object(
                flux_client,
                "_async_list_flux_resource",
                side_effect=ApiException(status=404),
            ),
            patch.object(flux_client, "async_get_flux_controllers", new_callable=AsyncMock, return_value=[]),
            caplog.at_level(logging.WARNING, logger="custom_components.fluxcd_k8s.api"),
        ):
            await flux_client.async_get_all_flux_resources()

        warning_records = [
            record
            for record in caplog.records
            if record.levelno >= logging.WARNING
            and record.name == _api_module.__name__
        ]
        assert not warning_records

    @pytest.mark.asyncio
    async def test_404_emits_debug_log(self, caplog):
        """A 404 ApiException should produce a DEBUG log about the CRD being unavailable."""
        flux_client = FluxKubernetesClient(hass=MagicMock(), access_mode="kubeconfig")
        flux_client._api_client = object()

        with (
            patch.object(_api_module, "CustomObjectsApi", return_value=MagicMock()),
            patch.object(
                flux_client,
                "_async_list_flux_resource",
                side_effect=ApiException(status=404),
            ),
            patch.object(flux_client, "async_get_flux_controllers", new_callable=AsyncMock, return_value=[]),
            caplog.at_level(logging.DEBUG, logger=_api_module.__name__),
        ):
            await flux_client.async_get_all_flux_resources()

        debug_messages = [
            r.message
            for r in caplog.records
            if r.levelno == logging.DEBUG and r.name == _api_module.__name__
        ]
        assert any("not available on this cluster" in msg for msg in debug_messages)

    @pytest.mark.asyncio
    async def test_non_404_api_exception_emits_warning(self, caplog):
        """A non-404 ApiException (e.g. 403 Forbidden) should still log at WARNING."""
        flux_client = FluxKubernetesClient(hass=MagicMock(), access_mode="kubeconfig")
        flux_client._api_client = object()

        with (
            patch.object(_api_module, "CustomObjectsApi", return_value=MagicMock()),
            patch.object(
                flux_client,
                "_async_list_flux_resource",
                side_effect=ApiException(status=403, reason="Forbidden"),
            ),
            patch.object(flux_client, "async_get_flux_controllers", new_callable=AsyncMock, return_value=[]),
            caplog.at_level(logging.WARNING, logger="custom_components.fluxcd_k8s.api"),
        ):
            await flux_client.async_get_all_flux_resources()

        assert any(
            "Failed to fetch" in record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )

    @pytest.mark.asyncio
    async def test_generic_exception_emits_warning(self, caplog):
        """A generic (non-ApiException) error should still log at WARNING."""
        flux_client = FluxKubernetesClient(hass=MagicMock(), access_mode="kubeconfig")
        flux_client._api_client = object()

        with (
            patch.object(_api_module, "CustomObjectsApi", return_value=MagicMock()),
            patch.object(
                flux_client,
                "_async_list_flux_resource",
                side_effect=RuntimeError("unexpected"),
            ),
            patch.object(flux_client, "async_get_flux_controllers", new_callable=AsyncMock, return_value=[]),
            caplog.at_level(logging.WARNING, logger="custom_components.fluxcd_k8s.api"),
        ):
            await flux_client.async_get_all_flux_resources()

        assert any(
            "Failed to fetch" in record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )

    @pytest.mark.asyncio
    async def test_404_returns_empty_list_for_missing_crd(self):
        """Resources from a 404-failing CRD should simply be absent from results."""
        flux_client = FluxKubernetesClient(hass=MagicMock(), access_mode="kubeconfig")
        flux_client._api_client = object()

        with (
            patch.object(_api_module, "CustomObjectsApi", return_value=MagicMock()),
            patch.object(
                flux_client,
                "_async_list_flux_resource",
                side_effect=ApiException(status=404),
            ),
            patch.object(flux_client, "async_get_flux_controllers", new_callable=AsyncMock, return_value=[]),
        ):
            result = await flux_client.async_get_all_flux_resources()

        assert result == []


class TestAsyncInit:
    """Tests for FluxKubernetesClient.async_init."""

    @pytest.mark.asyncio
    async def test_in_cluster_init_uses_executor_for_load_incluster_config(self):
        """load_incluster_config() must not run on the event loop."""
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(return_value=None)

        load_incluster_config = MagicMock()
        _api_module.config.load_incluster_config = load_incluster_config

        flux_client = FluxKubernetesClient(
            hass=hass, access_mode=_api_module.ACCESS_MODE_IN_CLUSTER
        )
        created_api_client = object()
        flux_client._async_create_api_client = AsyncMock(return_value=created_api_client)

        await flux_client.async_init()

        hass.async_add_executor_job.assert_awaited_once_with(load_incluster_config)
        load_incluster_config.assert_not_called()
        flux_client._async_create_api_client.assert_awaited_once_with()
        assert flux_client._api_client is created_api_client

    @pytest.mark.asyncio
    async def test_init_requires_hass(self):
        """hass must be provided to guarantee non-blocking in-cluster config loading."""
        with pytest.raises(ValueError, match="hass is required"):
            FluxKubernetesClient(hass=None, access_mode=_api_module.ACCESS_MODE_IN_CLUSTER)

    @pytest.mark.asyncio
    async def test_kubeconfig_init_loads_kubeconfig_in_executor(self, tmp_path):
        """Kubeconfig file reads must happen in the executor to avoid loop blocking."""
        kubeconfig_file = tmp_path / ".kube" / "config"
        kubeconfig_file.parent.mkdir()
        kubeconfig_file.write_text("apiVersion: v1\n")

        hass = MagicMock()
        hass.config.config_dir = str(tmp_path)

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        kubeconfig_node = object()
        merger = MagicMock(config=kubeconfig_node)
        api_client = object()
        kube_config_module = MagicMock(KubeConfigMerger=MagicMock(return_value=merger))
        load_kube_config_from_dict = AsyncMock()

        with (
            patch.object(
                _api_module.config, "kube_config", kube_config_module, create=True
            ),
            patch.object(
                _api_module.config,
                "load_kube_config_from_dict",
                load_kube_config_from_dict,
                create=True,
            ),
        ):
            flux_client = FluxKubernetesClient(
                hass=hass,
                access_mode="kubeconfig",
                kubeconfig_path=str(kubeconfig_file),
            )
            flux_client._async_create_api_client = AsyncMock(return_value=api_client)

            await flux_client.async_init()

            hass.async_add_executor_job.assert_awaited_once_with(
                flux_client._load_kubeconfig,
                str(kubeconfig_file),
                _api_module.get_search_dirs_for_hass(hass),
            )
            kube_config_module.KubeConfigMerger.assert_called_once_with(
                str(kubeconfig_file)
            )
            load_kube_config_from_dict.assert_awaited_once()
            called_kwargs = load_kube_config_from_dict.await_args.kwargs
            assert called_kwargs["config_dict"] is kubeconfig_node
            flux_client._async_create_api_client.assert_awaited_once_with(
                called_kwargs["client_configuration"]
            )
            assert flux_client._api_client is api_client

    @pytest.mark.asyncio
    async def test_kubeconfig_init_expands_home_shortcut(self, tmp_path, monkeypatch):
        """A '~/.kube/config' path must be expanded before the file is read."""
        monkeypatch.setenv("HOME", str(tmp_path))
        kubeconfig_file = tmp_path / ".kube" / "config"
        kubeconfig_file.parent.mkdir()
        kubeconfig_file.write_text("apiVersion: v1\n")

        hass = MagicMock()
        hass.config.config_dir = str(tmp_path)

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        merger = MagicMock(config={"apiVersion": "v1"})
        kube_config_module = MagicMock(KubeConfigMerger=MagicMock(return_value=merger))

        with (
            patch.object(
                _api_module.config, "kube_config", kube_config_module, create=True
            ),
            patch.object(
                _api_module.config,
                "load_kube_config_from_dict",
                AsyncMock(),
                create=True,
            ),
        ):
            flux_client = FluxKubernetesClient(
                hass=hass,
                access_mode="kubeconfig",
                kubeconfig_path="~/.kube/config",
            )
            flux_client._async_create_api_client = AsyncMock(return_value=object())

            await flux_client.async_init()

        kube_config_module.KubeConfigMerger.assert_called_once_with(
            str(kubeconfig_file)
        )

    @pytest.mark.asyncio
    async def test_kubeconfig_init_raises_when_no_kubeconfig_found(
        self, tmp_path, monkeypatch
    ):
        """A missing kubeconfig must fail with a clear, actionable error."""
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))

        hass = MagicMock()
        hass.config.config_dir = str(tmp_path)

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        flux_client = FluxKubernetesClient(
            hass=hass,
            access_mode="kubeconfig",
            kubeconfig_path=str(tmp_path / "nope" / "kubeconfig"),
        )

        with pytest.raises(KubeconfigNotFound, match="No kubeconfig file"):
            await flux_client.async_init()

    @pytest.mark.asyncio
    async def test_kubeconfig_init_reports_an_unparseable_file(self, tmp_path):
        """A file that exists but is not kubeconfig YAML must name the file.

        KubeConfigMerger fails inside the library on an empty file, so the
        error has to be translated rather than allowed to escape raw.
        """
        kubeconfig_file = tmp_path / "kubeconfig"
        kubeconfig_file.write_text("")

        hass = MagicMock()
        hass.config.config_dir = str(tmp_path)

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        kube_config_module = MagicMock(
            KubeConfigMerger=MagicMock(
                side_effect=TypeError("'NoneType' object does not support item assignment")
            )
        )

        with patch.object(
            _api_module.config, "kube_config", kube_config_module, create=True
        ):
            flux_client = FluxKubernetesClient(
                hass=hass,
                access_mode="kubeconfig",
                kubeconfig_path=str(kubeconfig_file),
            )

            with pytest.raises(KubeconfigNotFound, match="is empty or is not"):
                await flux_client.async_init()

    @pytest.mark.asyncio
    async def test_async_create_api_client_offloads_ssl_context_creation(self):
        """SSL context creation (incl. cert loading) must run in executor."""
        FluxKubernetesClient._cached_user_agent = None
        ssl_context = MagicMock()
        hass = MagicMock()
        hass.async_add_executor_job = AsyncMock(side_effect=[ssl_context, "35.0.1"])
        flux_client = FluxKubernetesClient(hass=hass, access_mode="kubeconfig")

        client_configuration = MagicMock()
        client_configuration.ssl_ca_cert = "/ca.crt"
        client_configuration.cert_file = "/tls.crt"
        client_configuration.key_file = "/tls.key"
        client_configuration.connection_pool_maxsize = 8
        client_configuration.tls_server_name = None
        client_configuration.proxy = None
        client_configuration.proxy_headers = None
        client_configuration.client_side_validation = True

        captured = {}

        def _build_api_client(configuration, context, user_agent):
            captured["cert_file_during_build"] = configuration.cert_file
            captured["key_file_during_build"] = configuration.key_file
            captured["context_during_build"] = context
            captured["user_agent_during_build"] = user_agent
            return object()

        flux_client._build_api_client_with_ssl_context = MagicMock(side_effect=_build_api_client)
        await flux_client._async_create_api_client(client_configuration)

        hass.async_add_executor_job.assert_any_await(
            flux_client._create_ssl_context,
            "/ca.crt",
            "/tls.crt",
            "/tls.key",
        )
        hass.async_add_executor_job.assert_any_await(
            flux_client._get_kubernetes_asyncio_version
        )
        assert captured["cert_file_during_build"] is None
        assert captured["key_file_during_build"] is None
        assert captured["context_during_build"] is ssl_context
        assert captured["user_agent_during_build"] == "OpenAPI-Generator/35.0.1/python"
        assert client_configuration.cert_file == "/tls.crt"
        assert client_configuration.key_file == "/tls.key"
