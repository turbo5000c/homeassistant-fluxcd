"""Pytest configuration for FluxCD integration tests."""

import importlib.util
import sys
import types
from pathlib import Path

# Set up a minimal fluxcd_k8s package so that models.py can use
# relative imports (e.g. from .const import ...) without triggering
# the real __init__.py which requires homeassistant.
_pkg_dir = Path(__file__).parent.parent / "custom_components" / "fluxcd_k8s"

_pkg = types.ModuleType("fluxcd_k8s")
_pkg.__path__ = [str(_pkg_dir)]
_pkg.__package__ = "fluxcd_k8s"
sys.modules["fluxcd_k8s"] = _pkg


def _load_submodule(name: str, filepath: Path):
    """Load a submodule of the fluxcd_k8s package by file path."""
    full_name = f"fluxcd_k8s.{name}"
    spec = importlib.util.spec_from_file_location(full_name, filepath)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "fluxcd_k8s"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


# Load const.py first (no dependencies), then models.py (imports .const)
_load_submodule("const", _pkg_dir / "const.py")
_load_submodule("models", _pkg_dir / "models.py")

# ---------------------------------------------------------------------------
# Minimal homeassistant stubs so that sensor.py can be imported in tests
# without a real Home Assistant installation.
# ---------------------------------------------------------------------------

def _make_ha_stub(name: str) -> types.ModuleType:
    """Return a stub module registered under the given dotted name."""
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_ha = _make_ha_stub("homeassistant")
_ha_components = _make_ha_stub("homeassistant.components")
_ha_sensor = _make_ha_stub("homeassistant.components.sensor")
_ha_sensor.SensorEntity = object
_ha_const = _make_ha_stub("homeassistant.const")


class _EntityCategory:  # noqa: D101
    DIAGNOSTIC = "diagnostic"


_ha_const.EntityCategory = _EntityCategory
_ha_core = _make_ha_stub("homeassistant.core")
_ha_core.HomeAssistant = object
_ha_helpers = _make_ha_stub("homeassistant.helpers")
_ha_ep = _make_ha_stub("homeassistant.helpers.entity_platform")
_ha_ep.AddEntitiesCallback = object
_ha_uc = _make_ha_stub("homeassistant.helpers.update_coordinator")


class _CoordinatorEntity:  # noqa: D101
    def __init__(self, coordinator, context=None):  # noqa: D107
        self.coordinator = coordinator

    def __class_getitem__(cls, item):  # noqa: D105
        return cls


_ha_uc.CoordinatorEntity = _CoordinatorEntity
_ha_uc.DataUpdateCoordinator = object
_ha_uc.UpdateFailed = Exception
_ha_cfg = _make_ha_stub("homeassistant.config_entries")
_ha_cfg.ConfigEntry = object
_ha_typing = _make_ha_stub("homeassistant.helpers.typing")

# Stubs for entity/device registry helpers imported by sensor.py
_ha_dr = _make_ha_stub("homeassistant.helpers.device_registry")
_ha_er = _make_ha_stub("homeassistant.helpers.entity_registry")


class _FakeEntityRegistry:
    """Minimal entity registry stub for tests."""

    def async_get_entity_id(self, platform, domain, unique_id):
        return None


class _FakeDeviceRegistry:
    """Minimal device registry stub for tests."""

    def async_get_device(self, identifiers):
        return None


_ha_dr.async_get = lambda hass: _FakeDeviceRegistry()
_ha_er.async_get = lambda hass: _FakeEntityRegistry()

# Stub third-party / deep-dependency modules so sensor.py's transitive
# imports (coordinator → api → kubernetes_asyncio) don't fail.
_make_ha_stub("kubernetes_asyncio")
_make_ha_stub("kubernetes_asyncio.client")
_make_ha_stub("kubernetes_asyncio.config")
_k8s_exc = _make_ha_stub("kubernetes_asyncio.client.exceptions")
_k8s_exc.ApiException = Exception

_api_stub = _make_ha_stub("fluxcd_k8s.api")
_api_stub.FluxKubernetesClient = object
_coord_stub = _make_ha_stub("fluxcd_k8s.coordinator")
_coord_stub.FluxCDCoordinator = _CoordinatorEntity

# Now load sensor.py which imports from the stubs above
_load_submodule("sensor", _pkg_dir / "sensor.py")
