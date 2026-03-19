"""The FluxCD integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .api import FluxKubernetesClient
from .const import (
    CONF_ACCESS_MODE,
    CONF_KUBECONFIG_PATH,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAMESPACE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FLUX_RESOURCES,
)
from .coordinator import FluxCDCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the FluxCD component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up FluxCD from a config entry."""
    _LOGGER.debug("Setting up %s integration", DOMAIN)

    # Create the Kubernetes API client
    k8s_client = FluxKubernetesClient(
        access_mode=entry.data[CONF_ACCESS_MODE],
        kubeconfig_path=entry.data.get(CONF_KUBECONFIG_PATH, ""),
        namespace=entry.data.get(CONF_NAMESPACE, DEFAULT_NAMESPACE),
        label_selector=entry.data.get(CONF_LABEL_SELECTOR, ""),
    )

    try:
        await k8s_client.async_init()
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Failed to initialize Kubernetes client: {err}"
        ) from err

    # Create the data update coordinator
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = FluxCDCoordinator(hass, entry, k8s_client, scan_interval)

    # Fetch initial data to verify the connection works
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in hass.data for access by platforms
    hass.data[DOMAIN][entry.entry_id] = coordinator

    device_reg = dr.async_get(hass)

    # ------------------------------------------------------------------
    # Cleanup: remove stale devices left by older versions of this
    # integration.  HA does not remove devices automatically on reload,
    # so orphaned entries accumulate across upgrades unless we explicitly
    # delete them here.
    #
    # Removed by this and older code revisions:
    #   • Hub device          identifiers={(DOMAIN, entry.entry_id)}
    #   • Category devices    identifiers={(DOMAIN, f"{entry_id}_Sources")}
    #                         identifiers={(DOMAIN, f"{entry_id}_Deployments")}
    #   • Kind devices        identifiers={(DOMAIN, f"{entry_id}_{kind}")}
    #     (all kinds — previously used as navigation nodes, now removed so
    #      individual resource devices appear at the top level)
    # ------------------------------------------------------------------
    _stale_identifiers: list[frozenset] = [
        frozenset({(DOMAIN, entry.entry_id)}),               # hub
        frozenset({(DOMAIN, f"{entry.entry_id}_Sources")}),  # category
        frozenset({(DOMAIN, f"{entry.entry_id}_Deployments")}),
    ]
    # Also remove all kind devices (current and future kinds)
    for flux_crd in FLUX_RESOURCES:
        _stale_identifiers.append(
            frozenset({(DOMAIN, f"{entry.entry_id}_{flux_crd['kind']}")})
        )
    for _idf in _stale_identifiers:
        _dev = device_reg.async_get_device(identifiers=_idf)
        if _dev is not None:
            device_reg.async_remove_device(_dev.id)

    # Set up all platforms for this integration
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading %s integration", DOMAIN)

    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Close the Kubernetes client and remove the config entry from hass.data
    if unload_ok:
        coordinator: FluxCDCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.k8s_client.async_close()

    return unload_ok
