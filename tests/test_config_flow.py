"""Tests for config_flow async behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PKG_DIR = Path(__file__).parent.parent / "custom_components" / "fluxcd_k8s"


def _stub_module(name: str) -> types.ModuleType:
    """Create and register a stub module by dotted name."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _ensure_import_stubs() -> None:
    """Ensure modules imported by config_flow.py exist for tests."""
    if "voluptuous" not in sys.modules:
        vol = _stub_module("voluptuous")
        vol.Schema = lambda *args, **kwargs: object()
        vol.Required = lambda *args, **kwargs: object()
        vol.Optional = lambda *args, **kwargs: object()
        vol.In = lambda *args, **kwargs: object()
        vol.All = lambda *args, **kwargs: object()
        vol.Coerce = lambda *args, **kwargs: object()
        vol.Range = lambda *args, **kwargs: object()

    # conftest already provides core HA stubs; extend what config_flow imports.
    ha_exceptions = sys.modules.get("homeassistant.exceptions") or _stub_module(
        "homeassistant.exceptions"
    )
    if not hasattr(ha_exceptions, "HomeAssistantError"):
        ha_exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})

    ha_def = sys.modules.get("homeassistant.data_entry_flow") or _stub_module(
        "homeassistant.data_entry_flow"
    )
    if not hasattr(ha_def, "FlowResult"):
        ha_def.FlowResult = dict

    ha_cfg = sys.modules.get("homeassistant.config_entries") or _stub_module(
        "homeassistant.config_entries"
    )
    if not hasattr(ha_cfg, "ConfigFlow"):
        class _StubConfigFlow:  # noqa: D401, D101
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        ha_cfg.ConfigFlow = _StubConfigFlow


def _load_config_flow_module():
    """Load config_flow.py with stubs (without Home Assistant installed)."""
    _ensure_import_stubs()

    full_name = "fluxcd_k8s._real_config_flow"
    if full_name in sys.modules:
        return sys.modules[full_name]

    spec = importlib.util.spec_from_file_location(full_name, _PKG_DIR / "config_flow.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "fluxcd_k8s"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_config_flow = _load_config_flow_module()
_const = sys.modules["fluxcd_k8s.const"]
_kubeconfig = sys.modules["fluxcd_k8s.kubeconfig"]


@pytest.fixture(autouse=True)
def _isolate_kubeconfig_search(monkeypatch):
    """Stop discovery from reaching a kubeconfig on the machine running tests."""
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.setattr(_kubeconfig, "DEFAULT_SEARCH_DIRS", ())


def _hass_with_config_dir(config_dir: str = "/config") -> AsyncMock:
    """Return a hass mock whose config directory is a real string."""
    hass = AsyncMock()
    hass.config = MagicMock()
    hass.config.config_dir = config_dir
    return hass


class TestValidateInput:
    @pytest.mark.asyncio
    async def test_kubeconfig_path_check_runs_in_executor(self):
        hass = _hass_with_config_dir()
        hass.async_add_executor_job = AsyncMock(return_value=None)

        data = {
            _const.CONF_ACCESS_MODE: _const.ACCESS_MODE_KUBECONFIG,
            _const.CONF_KUBECONFIG_PATH: "/does/not/exist",
        }

        with pytest.raises(_config_flow.InvalidKubeconfigPath):
            await _config_flow.validate_input(hass, data)

        hass.async_add_executor_job.assert_awaited_once_with(
            _config_flow.resolve_kubeconfig_path,
            "/does/not/exist",
            _config_flow.get_search_dirs_for_hass(hass),
        )

    @pytest.mark.asyncio
    async def test_kubeconfig_valid_path_passes_hass_to_client(self):
        hass = _hass_with_config_dir()
        hass.async_add_executor_job = AsyncMock(return_value="/does/exist")

        mock_client = MagicMock()
        mock_client.async_init = AsyncMock(return_value=None)
        mock_client.async_test_connection = AsyncMock(return_value=True)
        mock_client.async_close = AsyncMock(return_value=None)

        data = {
            _const.CONF_ACCESS_MODE: _const.ACCESS_MODE_KUBECONFIG,
            _const.CONF_KUBECONFIG_PATH: "/does/exist",
        }

        with patch.object(
            _config_flow, "FluxKubernetesClient", return_value=mock_client
        ) as mock_client_class:
            result = await _config_flow.validate_input(hass, data)

        hass.async_add_executor_job.assert_awaited_once_with(
            _config_flow.resolve_kubeconfig_path,
            "/does/exist",
            _config_flow.get_search_dirs_for_hass(hass),
        )
        mock_client_class.assert_called_once_with(
            hass=hass,
            access_mode=_const.ACCESS_MODE_KUBECONFIG,
            kubeconfig_path="/does/exist",
            namespace=_const.DEFAULT_NAMESPACE,
            label_selector="",
        )
        mock_client.async_init.assert_awaited_once()
        mock_client.async_test_connection.assert_awaited_once()
        mock_client.async_close.assert_awaited_once()
        assert result["title"] == "FluxCD (all namespaces)"

    @pytest.mark.asyncio
    async def test_tilde_kubeconfig_path_is_accepted(self, tmp_path, monkeypatch):
        """'~/.kube/config' must resolve instead of being rejected as missing."""
        monkeypatch.setenv("HOME", str(tmp_path))
        kube_dir = tmp_path / ".kube"
        kube_dir.mkdir()
        (kube_dir / "config").write_text("apiVersion: v1\n")

        hass = _hass_with_config_dir(str(tmp_path))

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        mock_client = MagicMock()
        mock_client.async_init = AsyncMock(return_value=None)
        mock_client.async_test_connection = AsyncMock(return_value=True)
        mock_client.async_close = AsyncMock(return_value=None)

        data = {
            _const.CONF_ACCESS_MODE: _const.ACCESS_MODE_KUBECONFIG,
            _const.CONF_KUBECONFIG_PATH: "~/.kube/config",
        }

        with patch.object(
            _config_flow, "FluxKubernetesClient", return_value=mock_client
        ) as mock_client_class:
            result = await _config_flow.validate_input(hass, data)

        # The unexpanded path is stored; expansion happens when it is used.
        assert mock_client_class.call_args.kwargs["kubeconfig_path"] == "~/.kube/config"
        assert result["title"] == "FluxCD (all namespaces)"

    @pytest.mark.asyncio
    async def test_empty_kubeconfig_path_discovers_config_dir_file(
        self, tmp_path, monkeypatch
    ):
        """An empty path falls back to a 'kubeconfig' file in the HA config dir."""
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
        (tmp_path / "kubeconfig").write_text("apiVersion: v1\n")

        hass = _hass_with_config_dir(str(tmp_path))

        async def _run_in_executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = AsyncMock(side_effect=_run_in_executor)

        mock_client = MagicMock()
        mock_client.async_init = AsyncMock(return_value=None)
        mock_client.async_test_connection = AsyncMock(return_value=True)
        mock_client.async_close = AsyncMock(return_value=None)

        data = {
            _const.CONF_ACCESS_MODE: _const.ACCESS_MODE_KUBECONFIG,
            _const.CONF_KUBECONFIG_PATH: "",
        }

        with patch.object(
            _config_flow, "FluxKubernetesClient", return_value=mock_client
        ):
            result = await _config_flow.validate_input(hass, data)

        assert result["title"] == "FluxCD (all namespaces)"

    @pytest.mark.asyncio
    async def test_kubeconfig_lost_during_validation_is_a_path_error(self):
        """KubeconfigNotFound must not be flattened into 'cannot connect'.

        The pre-check and the actual load are two separate filesystem scans, so
        the file can disappear in between; the user needs the path message.
        """
        hass = _hass_with_config_dir()
        hass.async_add_executor_job = AsyncMock(return_value="/was/here")

        mock_client = MagicMock()
        mock_client.async_init = AsyncMock(
            side_effect=_kubeconfig.KubeconfigNotFound("No kubeconfig file found.")
        )
        mock_client.async_close = AsyncMock(return_value=None)

        data = {
            _const.CONF_ACCESS_MODE: _const.ACCESS_MODE_KUBECONFIG,
            _const.CONF_KUBECONFIG_PATH: "/was/here",
        }

        with (
            patch.object(_config_flow, "FluxKubernetesClient", return_value=mock_client),
            pytest.raises(_config_flow.InvalidKubeconfigPath),
        ):
            await _config_flow.validate_input(hass, data)

        mock_client.async_close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_in_cluster_mode_skips_kubeconfig_lookup(self):
        """In-cluster mode must not look for a kubeconfig file."""
        hass = _hass_with_config_dir()
        hass.async_add_executor_job = AsyncMock()

        mock_client = MagicMock()
        mock_client.async_init = AsyncMock(return_value=None)
        mock_client.async_test_connection = AsyncMock(return_value=True)
        mock_client.async_close = AsyncMock(return_value=None)

        data = {_const.CONF_ACCESS_MODE: _const.ACCESS_MODE_IN_CLUSTER}

        with patch.object(
            _config_flow, "FluxKubernetesClient", return_value=mock_client
        ):
            result = await _config_flow.validate_input(hass, data)

        hass.async_add_executor_job.assert_not_awaited()
        assert result["title"] == "FluxCD (all namespaces)"
