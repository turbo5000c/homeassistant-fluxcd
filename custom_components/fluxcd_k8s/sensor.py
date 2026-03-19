"""Sensor platform for FluxCD resources."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FLUX_RESOURCES, STATE_UNKNOWN
from .coordinator import FluxCDCoordinator
from .models import FluxResource, _get_condition_flag

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

# Map resource kind to its display name for device naming
_KIND_TO_RESOURCE_TYPE: dict[str, str] = {
    crd["kind"]: crd["resource_type"] for crd in FLUX_RESOURCES
}

# Kind-specific icons for the main status sensor
_KIND_ICONS: dict[str, str] = {
    "GitRepository": "mdi:git",
    "HelmRepository": "mdi:package-variant-closed",
    "HelmChart": "mdi:chart-box-outline",
    "HelmRelease": "mdi:package-variant",
    "Kustomization": "mdi:puzzle-outline",
    "OCIRepository": "mdi:docker",
    "Bucket": "mdi:bucket-outline",
    "FluxInstance": "mdi:kubernetes",
    "ResourceSet": "mdi:layers-outline",
    "ArtifactGenerator": "mdi:file-code-outline",
    "ExternalArtifact": "mdi:download-box-outline",
    "ResourceSetInputProvider": "mdi:database-import-outline",
    "ControllerComponent": "mdi:cog-outline",
}

# Diagnostic sensors created for every FluxCD resource kind.
# Each entry: (attr_key, display_name_suffix, mdi_icon)
_COMMON_DIAGNOSTIC_SENSORS: list[tuple[str, str, str]] = [
    ("ready_condition", "Ready Condition", "mdi:check-circle-outline"),
    ("observed_generation", "Observed Generation", "mdi:counter"),
]

# Additional diagnostic sensors per resource kind
_KIND_EXTRA_DIAGNOSTIC_SENSORS: dict[str, list[tuple[str, str, str]]] = {
    "GitRepository": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "HelmRepository": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "HelmChart": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "OCIRepository": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "Bucket": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "HelmRelease": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("last_applied_revision", "Last Applied Revision", "mdi:tag-outline"),
    ],
    "Kustomization": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("last_applied_revision", "Last Applied Revision", "mdi:tag-outline"),
    ],
    "FluxInstance": [
        ("last_applied_revision", "Last Applied Revision", "mdi:tag-outline"),
    ],
    "ResourceSet": [
        ("interval", "Interval", "mdi:timer-outline"),
    ],
    "ArtifactGenerator": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "ExternalArtifact": [
        ("interval", "Interval", "mdi:timer-outline"),
        ("artifact_revision", "Artifact Revision", "mdi:tag-outline"),
    ],
    "ResourceSetInputProvider": [],
    "ControllerComponent": [
        ("desired_replicas", "Desired Replicas", "mdi:counter"),
        ("ready_replicas", "Ready Replicas", "mdi:counter"),
        ("available_replicas", "Available Replicas", "mdi:counter"),
    ],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FluxCD sensor entities from a config entry.

    Creates one primary status sensor and several diagnostic sensors for
    each FluxCD resource discovered in the Kubernetes cluster.
    """
    coordinator: FluxCDCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[SensorEntity] = []
    if coordinator.data:
        for resources in coordinator.data.values():
            for resource in resources:
                sensors.append(FluxCDResourceSensor(coordinator, entry, resource))
                sensors.extend(
                    _create_diagnostic_sensors(coordinator, entry, resource)
                )

    async_add_entities(sensors)

    # Track which unique IDs have already been added as entities
    known_ids: set[str] = {s.unique_id for s in sensors if s.unique_id}

    # Register a listener to add new entities when resources are discovered
    entry.async_on_unload(
        coordinator.async_add_listener(
            partial(
                _async_check_new_entities,
                coordinator,
                entry,
                async_add_entities,
                known_ids,
            )
        )
    )


def _async_check_new_entities(
    coordinator: FluxCDCoordinator,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    known_ids: set[str],
) -> None:
    """Check for new FluxCD resources and add entities for them."""
    if not coordinator.data:
        return

    new_sensors: list[SensorEntity] = []
    for resources in coordinator.data.values():
        for resource in resources:
            unique_id = _build_unique_id(entry.entry_id, resource)
            if unique_id not in known_ids:
                known_ids.add(unique_id)
                new_sensors.append(
                    FluxCDResourceSensor(coordinator, entry, resource)
                )
                for diag in _create_diagnostic_sensors(coordinator, entry, resource):
                    if diag.unique_id not in known_ids:
                        known_ids.add(diag.unique_id)
                        new_sensors.append(diag)

    if new_sensors:
        async_add_entities(new_sensors)


def _unique_id_key(entry_id: str, kind: str, namespace: str, name: str) -> str:
    """Return the raw unique-ID string for a resource (entry_id + kind + ns + name).

    This is the single source of truth for the unique-ID format.  All helpers
    and methods that need to build or match a unique ID must call this function
    instead of constructing the string themselves.
    """
    return f"{DOMAIN}_{entry_id}_{kind}_{namespace}_{name}"


def _device_identifier(
    entry_id: str, kind: str, namespace: str, name: str
) -> frozenset:
    """Return the device-registry identifier set for a FluxCD resource.

    This is the single source of truth for the device-identifier format.  All
    helpers and methods that need to build or match a device identifier must
    call this function instead of constructing the set themselves.
    """
    return frozenset({(DOMAIN, f"{entry_id}_{kind}_{namespace}_{name}")})


def _build_unique_id(entry_id: str, resource: FluxResource) -> str:
    """Build a unique ID for a FluxCD resource sensor.

    The ID encodes the config-entry, resource kind, namespace and name so
    that two resources that share the same namespace/name but have different
    kinds (e.g. a HelmRelease *and* a HelmRepository both called
    "traefik/traefik") always produce distinct unique IDs and are therefore
    registered as separate entities in Home Assistant.
    """
    return _unique_id_key(entry_id, resource.kind, resource.namespace, resource.name)


def _build_device_info(entry_id: str, resource: FluxResource) -> dict[str, Any]:
    """Build device_info for a single FluxCD resource instance.

    Each resource is its own top-level HA device.  There are no intermediate
    kind or category devices — resources appear directly in the integration's
    device list so users can navigate straight to a resource.

    The device name includes both the namespace/name *and* the resource kind
    (e.g. "traefik/traefik (Helm Release)").  This is important because it is
    common for multiple FluxCD resource types to share the same namespace and
    name (e.g. a HelmRelease *and* a HelmRepository both called
    "traefik/traefik").  Without the kind suffix those two devices would have
    identical display names in the HA UI, causing their entities to appear as
    duplicates.

    Resource identifiers include kind, namespace and name so that each
    Kubernetes resource maps to a stable, unique device.  If a resource is
    renamed in the cluster HA will treat it as a new device (the old one
    becomes orphaned), which is the expected behaviour for k8s-backed
    integrations.
    """
    kind = resource.kind
    resource_type = _KIND_TO_RESOURCE_TYPE.get(kind, kind)
    if kind == "ControllerComponent":
        resource_type = "Flux Controller"

    return {
        "identifiers": _device_identifier(entry_id, kind, resource.namespace, resource.name),
        # Include the resource kind in the name so that two resources sharing
        # the same namespace/name but of different kinds (e.g. a HelmRelease
        # *and* a HelmRepository both named "traefik/traefik") appear as
        # clearly distinct devices instead of merging into one in the HA UI.
        "name": f"{resource.namespace}/{resource.name} ({resource_type})",
        "manufacturer": "FluxCD",
        "model": resource_type,
        # No via_device: resource devices are top-level navigation nodes so
        # clicking one goes directly to that resource's entity page.
    }


def _create_diagnostic_sensors(
    coordinator: FluxCDCoordinator,
    entry: ConfigEntry,
    resource: FluxResource,
) -> list[FluxCDDiagnosticSensor]:
    """Create diagnostic sensor entities for a FluxCD resource."""
    defs: list[tuple[str, str, str]] = list(_COMMON_DIAGNOSTIC_SENSORS)
    defs.extend(_KIND_EXTRA_DIAGNOSTIC_SENSORS.get(resource.kind, []))
    return [
        FluxCDDiagnosticSensor(coordinator, entry, resource, attr_key, name, icon)
        for attr_key, name, icon in defs
    ]


class FluxCDResourceSensor(CoordinatorEntity[FluxCDCoordinator], SensorEntity):
    """Sensor entity representing a single FluxCD resource.

    The primary state is the ready status (ready, not_ready, progressing,
    suspended, or unknown).  Extra state attributes expose the most useful
    per-resource fields at a glance.  Detailed diagnostic data is split out
    into separate FluxCDDiagnosticSensor entities so that it appears in the
    "Diagnostic" section of the HA device page.

    Because has_entity_name is True, HA automatically prefixes this entity
    with the device name ("traefik/traefik") in global views while showing
    just "Status" on the device page — matching the Portainer-style layout.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FluxCDCoordinator,
        entry: ConfigEntry,
        resource: FluxResource,
    ) -> None:
        """Initialize the FluxCD resource sensor."""
        super().__init__(
            coordinator,
            context=_build_unique_id(entry.entry_id, resource),
        )

        self._entry_id = entry.entry_id
        self._resource_kind = resource.kind
        self._resource_name = resource.name
        self._resource_namespace = resource.namespace

        self._attr_unique_id = _build_unique_id(entry.entry_id, resource)
        self._attr_name = "Status"
        self._attr_icon = _KIND_ICONS.get(resource.kind, "mdi:kubernetes")
        self._attr_device_info = _build_device_info(entry.entry_id, resource)

    def _find_resource(self) -> FluxResource | None:
        """Find this sensor's resource in the coordinator data."""
        if not self.coordinator.data:
            return None
        resources = self.coordinator.data.get(self._resource_kind, [])
        for res in resources:
            if (
                res.name == self._resource_name
                and res.namespace == self._resource_namespace
            ):
                return res
        return None

    def _lookup_resource(
        self, kind: str, namespace: str, name: str
    ) -> tuple[str | None, str | None]:
        """Look up a FluxCD resource's HA entity ID and device ID.

        Uses the HA entity and device registries to resolve a (kind, namespace,
        name) triple to the entity_id of the target resource's Status sensor and
        the internal HA device ID of its device entry.

        Returns (entity_id, device_id) where either value may be None if the
        target resource has not been registered in HA yet, or if hass is not
        available.
        """
        if self.hass is None:
            return None, None

        target_unique_id = _unique_id_key(self._entry_id, kind, namespace, name)
        entity_reg = er.async_get(self.hass)
        entity_id = entity_reg.async_get_entity_id("sensor", DOMAIN, target_unique_id)

        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get_device(
            identifiers=_device_identifier(self._entry_id, kind, namespace, name)
        )
        device_id = device.id if device else None

        return entity_id, device_id

    def _resolve_relationships(self, resource: FluxResource) -> dict[str, Any]:
        """Resolve source/chart refs to HA entity and device IDs.

        For resources that carry normalized source_ref_* or chart_ref_* fields
        (Kustomization, HelmChart, HelmRelease, ResourceSet, …) we look up the
        referenced resource in the HA entity/device registries and expose the
        resolved IDs as attributes.  This allows dashboards and automations to
        navigate directly to the linked resource entity.

        When a namespace is not specified in the ref we fall back to the
        referencing resource's own namespace, matching Flux's defaulting
        behaviour.
        """
        result: dict[str, Any] = {}
        extra = resource.extra_attributes

        # --- source ref (all relevant resource types) ---
        source_kind = extra.get("source_ref_kind", "")
        source_name = extra.get("source_ref_name", "")
        # Flux defaults the sourceRef namespace to the resource's own namespace
        source_ns = extra.get("source_ref_namespace") or resource.namespace

        if source_kind and source_name:
            entity_id, device_id = self._lookup_resource(
                source_kind, source_ns, source_name
            )
            if entity_id:
                result["source_entity_id"] = entity_id
            if device_id:
                result["source_device_id"] = device_id

        # --- chart ref (HelmRelease spec.chartRef — direct HelmChart pointer) ---
        chart_ref_kind = extra.get("chart_ref_kind", "")
        chart_ref_name = extra.get("chart_ref_name", "")
        chart_ref_ns = extra.get("chart_ref_namespace") or resource.namespace

        if chart_ref_kind and chart_ref_name:
            entity_id, device_id = self._lookup_resource(
                chart_ref_kind, chart_ref_ns, chart_ref_name
            )
            if entity_id:
                result["chart_entity_id"] = entity_id
            if device_id:
                result["chart_device_id"] = device_id

        return result

    @property
    def native_value(self) -> str:
        """Return the ready status of the FluxCD resource."""
        resource = self._find_resource()
        if resource is None:
            return STATE_UNKNOWN
        return resource.ready_status

    @property
    def available(self) -> bool:
        """Return True if the coordinator has data."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return primary state attributes for the FluxCD resource."""
        resource = self._find_resource()
        if resource is None:
            return {}

        attrs: dict[str, Any] = {
            "category": resource.category.lower(),
            "kind": resource.kind,
            "namespace": resource.namespace,
            "resource_name": resource.name,
            "suspended": resource.suspend,
            "reason": resource.reason,
            "message": resource.message,
            "reconcile_time": resource.reconcile_time,
        }

        # Add kind-specific primary attributes (source, chart, version, summary, …)
        attrs.update(resource.extra_attributes)

        # Add resolved entity/device relationships for source and chart refs
        attrs.update(self._resolve_relationships(resource))

        # Remove empty-string and None values to avoid UI noise
        return {k: v for k, v in attrs.items() if v is not None and v != ""}


class FluxCDDiagnosticSensor(CoordinatorEntity[FluxCDCoordinator], SensorEntity):
    """Diagnostic sensor exposing a single low-level attribute of a FluxCD resource.

    These sensors appear under the "Diagnostic" section of the HA device page,
    keeping the primary sensor uncluttered while still surfacing useful data.

    Because has_entity_name is True, HA prefixes the entity with the device
    name in global views (e.g. "traefik/traefik Ready Condition") while
    showing just "Ready Condition" on the device page.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FluxCDCoordinator,
        entry: ConfigEntry,
        resource: FluxResource,
        attr_key: str,
        display_name: str,
        icon: str,
    ) -> None:
        """Initialize the diagnostic sensor."""
        resource_unique_id = _build_unique_id(entry.entry_id, resource)
        super().__init__(coordinator, context=resource_unique_id)

        self._resource_kind = resource.kind
        self._resource_name = resource.name
        self._resource_namespace = resource.namespace
        self._attr_key = attr_key

        self._attr_unique_id = f"{resource_unique_id}_{attr_key}"
        self._attr_name = display_name
        self._attr_icon = icon
        self._attr_device_info = _build_device_info(entry.entry_id, resource)

    def _find_resource(self) -> FluxResource | None:
        """Find this sensor's resource in the coordinator data."""
        if not self.coordinator.data:
            return None
        resources = self.coordinator.data.get(self._resource_kind, [])
        for res in resources:
            if (
                res.name == self._resource_name
                and res.namespace == self._resource_namespace
            ):
                return res
        return None

    @property
    def native_value(self) -> Any:
        """Return the value of the diagnostic attribute."""
        resource = self._find_resource()
        if resource is None:
            return None

        # Special-cased fields that live on the model or are derived from conditions
        if self._attr_key == "observed_generation":
            return resource.observed_generation
        if self._attr_key == "ready_condition":
            return _get_condition_flag(resource.conditions, "Ready")
        if self._attr_key == "artifact_in_storage":
            return _get_condition_flag(resource.conditions, "ArtifactInStorage")

        # Controller replica counts are stored in extra_attributes
        if self._attr_key in ("desired_replicas", "ready_replicas", "available_replicas"):
            return resource.extra_attributes.get(self._attr_key)

        # All other diagnostic attributes come from the diagnostic_attributes dict
        return resource.diagnostic_attributes.get(self._attr_key)

    @property
    def available(self) -> bool:
        """Return True if the coordinator has data."""
        return self.coordinator.last_update_success
