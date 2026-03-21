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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNotFoundHandling:
    """Verify that 404 ApiException is handled silently at DEBUG level."""

    @pytest.mark.asyncio
    async def test_404_does_not_emit_warning(self, caplog):
        """A 404 ApiException should be logged at DEBUG, not WARNING."""
        flux_client = FluxKubernetesClient(access_mode="kubeconfig")
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
        flux_client = FluxKubernetesClient(access_mode="kubeconfig")
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
        flux_client = FluxKubernetesClient(access_mode="kubeconfig")
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
        flux_client = FluxKubernetesClient(access_mode="kubeconfig")
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
        flux_client = FluxKubernetesClient(access_mode="kubeconfig")
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

