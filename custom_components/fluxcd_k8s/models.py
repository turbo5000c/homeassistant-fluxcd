"""Data models for FluxCD resources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .const import (
    CATEGORY_CONTROLLERS,
    STATE_DEGRADED,
    STATE_NOT_READY,
    STATE_PROGRESSING,
    STATE_READY,
    STATE_SUSPENDED,
    STATE_UNKNOWN,
)


@dataclass
class FluxCondition:
    """Represents a single Flux status condition."""

    type: str
    status: str
    reason: str
    message: str
    last_transition_time: str


@dataclass
class FluxResource:
    """Base model for a FluxCD resource.

    Contains the common fields extracted from metadata, spec, and status
    of FluxCD custom resources.
    """

    kind: str
    name: str
    namespace: str
    category: str
    ready_status: str  # "ready", "not_ready", "progressing", "suspended", "unknown"
    message: str
    reason: str
    reconcile_time: str
    suspend: bool
    observed_generation: int | None
    conditions: list[FluxCondition] = field(default_factory=list)
    extra_attributes: dict[str, Any] = field(default_factory=dict)
    diagnostic_attributes: dict[str, Any] = field(default_factory=dict)


def parse_conditions(status: dict[str, Any]) -> list[FluxCondition]:
    """Parse the conditions list from a Flux resource status.

    Flux resources store conditions in status.conditions as a list of
    objects with type, status, reason, message, and lastTransitionTime.
    """
    conditions: list[FluxCondition] = []
    for cond in status.get("conditions", []):
        conditions.append(
            FluxCondition(
                type=cond.get("type", ""),
                status=cond.get("status", ""),
                reason=cond.get("reason", ""),
                message=cond.get("message", ""),
                last_transition_time=cond.get("lastTransitionTime", ""),
            )
        )
    return conditions


def get_ready_condition(
    conditions: list[FluxCondition],
) -> FluxCondition | None:
    """Find the 'Ready' condition from a list of Flux conditions."""
    for cond in conditions:
        if cond.type == "Ready":
            return cond
    return None


def determine_ready_status(conditions: list[FluxCondition]) -> str:
    """Determine the overall ready status from conditions.

    Returns 'ready', 'not_ready', 'progressing', or 'unknown'.
    A resource is considered progressing when it has a Reconciling
    condition with status 'True' and is not yet ready.
    """
    ready = get_ready_condition(conditions)
    if ready is not None and ready.status == "True":
        return STATE_READY

    # Check for an active Reconciling condition before reporting not_ready/unknown
    for cond in conditions:
        if cond.type == "Reconciling" and cond.status == "True":
            return STATE_PROGRESSING

    if ready is not None and ready.status == "False":
        return STATE_NOT_READY

    return STATE_UNKNOWN


def _get_condition_flag(conditions: list[FluxCondition], cond_type: str) -> bool | None:
    """Return True/False when a named condition exists, or None when absent."""
    for cond in conditions:
        if cond.type == cond_type:
            return cond.status == "True"
    return None


def _format_source_ref(kind: str, name: str, namespace: str = "") -> str:
    """Format a source reference as 'Kind/name' or 'Kind/namespace/name'."""
    if namespace:
        return f"{kind}/{namespace}/{name}"
    return f"{kind}/{name}"


def parse_flux_resource(
    raw: dict[str, Any], kind: str, category: str = ""
) -> FluxResource:
    """Parse a raw Kubernetes custom object into a FluxResource.

    Extracts common fields from metadata, spec, and status, then
    delegates to kind-specific parsers for extra attributes.
    """
    metadata = raw.get("metadata", {})
    spec = raw.get("spec", {})
    status = raw.get("status", {})

    conditions = parse_conditions(status)
    ready_status = determine_ready_status(conditions)
    ready_cond = get_ready_condition(conditions)

    # Suspended resources override the derived ready status
    if spec.get("suspend", False):
        ready_status = STATE_SUSPENDED

    resource = FluxResource(
        kind=kind,
        name=metadata.get("name", ""),
        namespace=metadata.get("namespace", ""),
        category=category,
        ready_status=ready_status,
        message=ready_cond.message if ready_cond else "",
        reason=ready_cond.reason if ready_cond else "",
        reconcile_time=ready_cond.last_transition_time if ready_cond else "",
        suspend=spec.get("suspend", False),
        observed_generation=status.get("observedGeneration"),
        conditions=conditions,
    )

    # Parse kind-specific primary and diagnostic attributes
    parser = _KIND_ATTR_PARSERS.get(kind)
    if parser is not None:
        primary, diagnostic = parser(spec, status)
        resource.extra_attributes = primary
        resource.diagnostic_attributes = diagnostic

    # Compute and store a human-readable summary
    summary = _compute_summary(resource)
    if summary:
        resource.extra_attributes["summary"] = summary

    return resource


def _compute_summary(resource: FluxResource) -> str:
    """Compute a short human-readable summary for the resource."""
    attrs = resource.extra_attributes
    kind = resource.kind
    name = resource.name

    if kind == "HelmChart":
        chart = attrs.get("chart", name)
        version = attrs.get("version", "")
        source = attrs.get("source", "")
        parts = [p for p in [chart, version] if p]
        base = " ".join(parts)
        return f"{base} from {source}" if source else base

    if kind == "HelmRelease":
        chart = attrs.get("chart_name", name)
        version = attrs.get("chart_version", "")
        source = attrs.get("source", "")
        parts = [p for p in [chart, version] if p]
        base = " ".join(parts)
        return f"{base} from {source}" if source else base

    if kind in ("GitRepository", "OCIRepository", "HelmRepository", "ExternalArtifact"):
        url = attrs.get("url", "")
        ref = (
            attrs.get("branch")
            or attrs.get("tag")
            or attrs.get("semver")
            or attrs.get("commit")
            or ""
        )
        base = f"{name} {ref}".strip() if ref else name
        return f"{base} from {url}" if url else base

    if kind == "Bucket":
        bucket = attrs.get("bucket_name", name)
        endpoint = attrs.get("endpoint", "")
        return f"{bucket} from {endpoint}" if endpoint else bucket

    if kind == "Kustomization":
        path = attrs.get("path", "")
        source = attrs.get("source", "")
        base = f"{name}{' ' + path if path else ''}"
        return f"{base} from {source}" if source else base

    if kind == "FluxInstance":
        version = attrs.get("distribution_version", "")
        return f"FluxCD {version}".strip() if version else "FluxCD"

    if kind in ("ResourceSet", "ResourceSetInputProvider"):
        source = attrs.get("source", "")
        return f"{name} from {source}" if source else name

    if kind == "ArtifactGenerator":
        return name

    return ""


# ---------------------------------------------------------------------------
# Kind-specific attribute parsers
# Each returns (primary_attrs, diagnostic_attrs).
# ---------------------------------------------------------------------------


def _parse_git_repository_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract GitRepository-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    ref = spec.get("ref", {})
    primary: dict[str, Any] = {
        "url": spec.get("url", ""),
        "branch": ref.get("branch", ""),
        "tag": ref.get("tag", ""),
        "semver": ref.get("semver", ""),
        "commit": ref.get("commit", ""),
    }
    diagnostic: dict[str, Any] = {
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
        "interval": spec.get("interval", ""),
    }
    return primary, diagnostic


def _parse_kustomization_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract Kustomization-specific attributes from spec and status."""
    source_ref = spec.get("sourceRef", {})
    source_kind = source_ref.get("kind", "")
    source_name = source_ref.get("name", "")
    source_namespace = source_ref.get("namespace", "")
    primary: dict[str, Any] = {
        "path": spec.get("path", ""),
        "prune": spec.get("prune", False),
        "source": _format_source_ref(source_kind, source_name, source_namespace)
        if source_kind
        else "",
        # Normalized ref fields for entity relationship resolution
        "source_ref_kind": source_kind,
        "source_ref_name": source_name,
        "source_ref_namespace": source_namespace,
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "last_applied_revision": status.get("lastAppliedRevision", ""),
        "last_attempted_revision": status.get("lastAttemptedRevision", ""),
    }
    return primary, diagnostic


def _parse_helm_release_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract HelmRelease-specific attributes from spec and status.

    HelmRelease supports two chart-referencing styles:
    - spec.chart.spec.sourceRef  — inline chart spec with a source reference
    - spec.chartRef              — direct reference to a HelmChart resource (Flux v2.3+)

    We parse both and expose separate source_ref_* and chart_ref_* fields so
    that the sensor layer can resolve either to a linked HA entity/device.
    """
    chart_spec = spec.get("chart", {}).get("spec", {})
    source_ref = chart_spec.get("sourceRef", {})
    source_kind = source_ref.get("kind", "")
    source_name = source_ref.get("name", "")
    source_namespace = source_ref.get("namespace", "")

    # spec.chartRef is used when the HelmRelease points directly at a
    # HelmChart resource instead of embedding a chart spec inline.
    chart_ref = spec.get("chartRef", {})
    chart_ref_kind = chart_ref.get("kind", "")
    chart_ref_name = chart_ref.get("name", "")
    chart_ref_namespace = chart_ref.get("namespace", "")

    primary: dict[str, Any] = {
        "chart_name": chart_spec.get("chart", ""),
        "chart_version": chart_spec.get("version", ""),
        "source": _format_source_ref(source_kind, source_name, source_namespace) if source_kind else "",
        # Normalized ref fields for entity relationship resolution
        "source_ref_kind": source_kind,
        "source_ref_name": source_name,
        "source_ref_namespace": source_namespace,
        # Direct HelmChart reference (Flux v2.3+ chartRef)
        "chart_ref_kind": chart_ref_kind,
        "chart_ref_name": chart_ref_name,
        "chart_ref_namespace": chart_ref_namespace,
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "last_applied_revision": status.get("lastAppliedRevision", ""),
        "last_attempted_revision": status.get("lastAttemptedRevision", ""),
        "last_release_revision": status.get("lastReleaseRevision"),
    }
    return primary, diagnostic


def _parse_helm_repository_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract HelmRepository-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    primary: dict[str, Any] = {
        "url": spec.get("url", ""),
        "repo_type": spec.get("type", "default"),
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_helm_chart_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract HelmChart-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    source_ref = spec.get("sourceRef", {})
    source_kind = source_ref.get("kind", "")
    source_name = source_ref.get("name", "")
    source_namespace = source_ref.get("namespace", "")
    primary: dict[str, Any] = {
        "chart": spec.get("chart", ""),
        "version": spec.get("version", ""),
        "source": _format_source_ref(source_kind, source_name, source_namespace)
        if source_kind
        else "",
        # Normalized ref fields for entity relationship resolution
        "source_ref_kind": source_kind,
        "source_ref_name": source_name,
        "source_ref_namespace": source_namespace,
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_bucket_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract Bucket-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    primary: dict[str, Any] = {
        "bucket_name": spec.get("bucketName", ""),
        "endpoint": spec.get("endpoint", ""),
        "provider": spec.get("provider", "generic"),
        "region": spec.get("region", ""),
        "prefix": spec.get("prefix", ""),
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_oci_repository_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract OCIRepository-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    ref = spec.get("ref", {})
    primary: dict[str, Any] = {
        "url": spec.get("url", ""),
        "tag": ref.get("tag", ""),
        "semver": ref.get("semver", ""),
        "digest": ref.get("digest", ""),
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_flux_instance_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract FluxInstance-specific attributes from spec and status."""
    distribution = spec.get("distribution", {})
    primary: dict[str, Any] = {
        "distribution_version": distribution.get("version", ""),
        "distribution_registry": distribution.get("registry", ""),
        "cluster_domain": spec.get("cluster", {}).get("domain", ""),
    }
    diagnostic: dict[str, Any] = {
        "last_applied_revision": status.get("lastAppliedRevision", ""),
        "last_attempted_revision": status.get("lastAttemptedRevision", ""),
    }
    return primary, diagnostic


def _parse_resource_set_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract ResourceSet-specific attributes from spec and status."""
    input_ref = spec.get("inputRef", {})
    input_kind = input_ref.get("kind", "")
    input_name = input_ref.get("name", "")
    primary: dict[str, Any] = {
        "source": _format_source_ref(input_kind, input_name) if input_kind else "",
        # Normalized ref fields for entity relationship resolution
        "source_ref_kind": input_kind,
        "source_ref_name": input_name,
        "source_ref_namespace": "",
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
    }
    return primary, diagnostic


def _parse_artifact_generator_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract ArtifactGenerator-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    primary: dict[str, Any] = {}
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_external_artifact_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract ExternalArtifact-specific attributes from spec and status."""
    artifact = status.get("artifact", {})
    primary: dict[str, Any] = {
        "url": spec.get("url", ""),
    }
    diagnostic: dict[str, Any] = {
        "interval": spec.get("interval", ""),
        "artifact_revision": artifact.get("revision", ""),
        "artifact_checksum": artifact.get("digest", ""),
    }
    return primary, diagnostic


def _parse_resource_set_input_provider_attrs(
    spec: dict[str, Any], status: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract ResourceSetInputProvider-specific attributes from spec and status."""
    resource_ref = spec.get("resourceRef", {})
    resource_kind = resource_ref.get("kind", "")
    resource_name = resource_ref.get("name", "")
    resource_namespace = resource_ref.get("namespace", "")
    primary: dict[str, Any] = {
        "source": _format_source_ref(
            resource_kind, resource_name, resource_namespace
        )
        if resource_kind
        else "",
        # Normalized ref fields for entity relationship resolution
        "source_ref_kind": resource_kind,
        "source_ref_name": resource_name,
        "source_ref_namespace": resource_namespace,
    }
    diagnostic: dict[str, Any] = {}
    return primary, diagnostic


# Map resource kind to its attribute parser
_KIND_ATTR_PARSERS: dict[
    str,
    Callable[
        [dict[str, Any], dict[str, Any]],
        tuple[dict[str, Any], dict[str, Any]],
    ],
] = {
    "GitRepository": _parse_git_repository_attrs,
    "Kustomization": _parse_kustomization_attrs,
    "HelmRelease": _parse_helm_release_attrs,
    "HelmRepository": _parse_helm_repository_attrs,
    "HelmChart": _parse_helm_chart_attrs,
    "Bucket": _parse_bucket_attrs,
    "OCIRepository": _parse_oci_repository_attrs,
    "FluxInstance": _parse_flux_instance_attrs,
    "ResourceSet": _parse_resource_set_attrs,
    "ArtifactGenerator": _parse_artifact_generator_attrs,
    "ExternalArtifact": _parse_external_artifact_attrs,
    "ResourceSetInputProvider": _parse_resource_set_input_provider_attrs,
}


# ---------------------------------------------------------------------------
# FluxCD controller component parsing
# ---------------------------------------------------------------------------


def _determine_controller_status(
    desired: int,
    ready: int,
    available: int,
    conditions: list[dict[str, Any]],
) -> str:
    """Derive a controller ready status from Deployment replica counts and conditions.

    Status mapping:
    - progressing: a Progressing condition is active (rolling update in progress)
    - ready: all desired replicas are available and ready
    - degraded: some (but not all) replicas are available
    - not_ready: no replicas are available
    - unknown: replica counts are unavailable
    """
    # Check for an active Progressing condition first
    for cond in conditions:
        if cond.get("type") == "Progressing" and cond.get("status") == "True":
            reason = cond.get("reason", "")
            # "NewReplicaSetAvailable" means the rollout finished — not progressing
            if reason != "NewReplicaSetAvailable":
                return STATE_PROGRESSING

    if desired <= 0:
        return STATE_UNKNOWN

    if available >= desired and ready >= desired:
        return STATE_READY

    if available > 0:
        return STATE_DEGRADED

    return STATE_NOT_READY


def parse_controller_deployment(raw: dict[str, Any]) -> FluxResource:
    """Parse a raw Kubernetes Deployment object into a FluxResource.

    Converts the Deployment's replica counts and conditions into the standard
    FluxResource model so that controller components can be handled by the
    same sensor infrastructure as CRD resources.
    """
    metadata = raw.get("metadata", {})
    spec = raw.get("spec", {})
    status = raw.get("status", {})

    name = metadata.get("name", "")
    namespace = metadata.get("namespace", "")

    desired_raw = spec.get("replicas")
    desired: int = desired_raw if desired_raw is not None else 1
    ready_replicas: int = status.get("readyReplicas") or 0
    available_replicas: int = status.get("availableReplicas") or 0
    observed_generation: int | None = status.get("observedGeneration")

    raw_conditions: list[dict[str, Any]] = status.get("conditions", [])

    ready_status = _determine_controller_status(
        desired, ready_replicas, available_replicas, raw_conditions
    )

    # Convert Deployment conditions to FluxConditions for a consistent interface
    flux_conditions: list[FluxCondition] = []
    last_transition_time = ""
    message = ""
    reason = ""
    for cond in raw_conditions:
        flux_conditions.append(
            FluxCondition(
                type=cond.get("type", ""),
                status=cond.get("status", ""),
                reason=cond.get("reason", ""),
                message=cond.get("message", ""),
                last_transition_time=cond.get("lastTransitionTime", ""),
            )
        )
        # Use the Available condition as the primary message/reason source
        if cond.get("type") == "Available":
            message = cond.get("message", "")
            reason = cond.get("reason", "")
            last_transition_time = cond.get("lastTransitionTime", "")

    # Extract image version tag from the first container image (e.g. v2.3.0)
    containers: list[dict[str, Any]] = (
        spec.get("template", {}).get("spec", {}).get("containers", [])
    )
    image_tag = ""
    if containers:
        image: str = containers[0].get("image", "")
        if ":" in image:
            image_tag = image.rsplit(":", 1)[-1]

    extra_attributes: dict[str, Any] = {
        "desired_replicas": desired,
        "ready_replicas": ready_replicas,
        "available_replicas": available_replicas,
    }
    if image_tag:
        extra_attributes["version"] = image_tag

    return FluxResource(
        kind="ControllerComponent",
        name=name,
        namespace=namespace,
        category=CATEGORY_CONTROLLERS,
        ready_status=ready_status,
        message=message,
        reason=reason,
        reconcile_time=last_transition_time,
        suspend=False,
        observed_generation=observed_generation,
        conditions=flux_conditions,
        extra_attributes=extra_attributes,
        diagnostic_attributes={},
    )
