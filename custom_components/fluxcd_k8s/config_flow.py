"""Config flow for FluxCD integration."""

from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import FluxKubernetesClient
from .const import (
    ACCESS_MODE_IN_CLUSTER,
    ACCESS_MODE_KUBECONFIG,
    CONF_ACCESS_MODE,
    CONF_KUBECONFIG_PATH,
    CONF_LABEL_SELECTOR,
    CONF_NAMESPACE,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAMESPACE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_MODE, default=ACCESS_MODE_KUBECONFIG): vol.In(
            {
                ACCESS_MODE_IN_CLUSTER: "In-Cluster",
                ACCESS_MODE_KUBECONFIG: "Kubeconfig File",
            }
        ),
        vol.Optional(CONF_KUBECONFIG_PATH, default=""): str,
        vol.Optional(CONF_NAMESPACE, default=DEFAULT_NAMESPACE): str,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
        vol.Optional(CONF_LABEL_SELECTOR, default=""): str,
    }
)


async def validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input by testing the Kubernetes connection.

    Creates a temporary client and attempts to connect to the cluster.
    Raises CannotConnect if the connection test fails.
    """
    access_mode = data[CONF_ACCESS_MODE]
    kubeconfig_path = data.get(CONF_KUBECONFIG_PATH, "")

    # Validate kubeconfig path if specified
    if access_mode == ACCESS_MODE_KUBECONFIG and kubeconfig_path:
        if not os.path.isfile(kubeconfig_path):
            raise InvalidKubeconfigPath

    k8s_client = FluxKubernetesClient(
        access_mode=access_mode,
        kubeconfig_path=kubeconfig_path,
        namespace=data.get(CONF_NAMESPACE, DEFAULT_NAMESPACE),
        label_selector=data.get(CONF_LABEL_SELECTOR, ""),
    )

    try:
        await k8s_client.async_init()
        if not await k8s_client.async_test_connection():
            raise CannotConnect
    except CannotConnect:
        raise
    except InvalidKubeconfigPath:
        raise
    except Exception as err:
        _LOGGER.exception("Unexpected error during connection test")
        raise CannotConnect from err
    finally:
        await k8s_client.async_close()

    # Generate a title based on access mode and namespace
    namespace = data.get(CONF_NAMESPACE, DEFAULT_NAMESPACE) or "all namespaces"
    title = f"FluxCD ({namespace})"
    return {"title": title}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FluxCD."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidKubeconfigPath:
                errors["base"] = "invalid_kubeconfig_path"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create a unique ID incorporating access mode, kubeconfig path,
                # namespace, and label selector to allow multiple configurations
                namespace = user_input.get(CONF_NAMESPACE, DEFAULT_NAMESPACE) or "all"
                kubeconfig = user_input.get(CONF_KUBECONFIG_PATH, "")
                label_sel = user_input.get(CONF_LABEL_SELECTOR, "")
                unique_id = (
                    f"{user_input[CONF_ACCESS_MODE]}_{kubeconfig}_{namespace}"
                    f"_{label_sel}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect to the Kubernetes cluster."""


class InvalidKubeconfigPath(HomeAssistantError):
    """Error to indicate the kubeconfig path is invalid."""
