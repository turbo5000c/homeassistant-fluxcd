"""Data update coordinator for FluxCD resources."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import FluxKubernetesClient
from .const import DOMAIN
from .models import FluxResource

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class FluxCDCoordinator(DataUpdateCoordinator[dict[str, list[FluxResource]]]):
    """Coordinator to manage fetching FluxCD resources from Kubernetes.

    Polls all four FluxCD resource kinds on a configurable interval and
    stores them as a dict keyed by resource kind.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        k8s_client: FluxKubernetesClient,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.k8s_client = k8s_client

    async def _async_update_data(self) -> dict[str, list[FluxResource]]:
        """Fetch all FluxCD resources from the Kubernetes cluster.

        Returns a dict keyed by resource kind (e.g. 'GitRepository') with
        lists of FluxResource objects as values.
        """
        try:
            resources = await self.k8s_client.async_get_all_flux_resources()
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching FluxCD resources: {err}"
            ) from err

        # Organize resources by kind for easy lookup
        result: dict[str, list[FluxResource]] = {}
        for resource in resources:
            result.setdefault(resource.kind, []).append(resource)

        _LOGGER.debug(
            "Fetched FluxCD resources: %s",
            {k: len(v) for k, v in result.items()},
        )
        return result
