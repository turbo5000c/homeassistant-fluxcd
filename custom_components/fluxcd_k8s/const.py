"""Constants for the FluxCD integration."""

from __future__ import annotations

# Domain name for this integration
DOMAIN = "fluxcd_k8s"

# Configuration keys
CONF_ACCESS_MODE = "access_mode"
CONF_KUBECONFIG_PATH = "kubeconfig_path"
CONF_NAMESPACE = "namespace"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LABEL_SELECTOR = "label_selector"

# Access modes
ACCESS_MODE_IN_CLUSTER = "in_cluster"
ACCESS_MODE_KUBECONFIG = "kubeconfig"

# Default values
DEFAULT_NAME = "FluxCD"
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_NAMESPACE = ""  # empty means all namespaces

# Categories
CATEGORY_SOURCES = "Sources"
CATEGORY_DEPLOYMENTS = "Deployments"
CATEGORY_CONTROLLERS = "Controllers"

# ---------------------------------------------------------------------------
# FluxCD CRD definitions
# Each entry: group, version, plural, kind, category, resource_type
# ---------------------------------------------------------------------------

# Sources (source.toolkit.fluxcd.io)
FLUX_GITREPOSITORY = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1",
    "plural": "gitrepositories",
    "kind": "GitRepository",
    "category": CATEGORY_SOURCES,
    "resource_type": "Git Repositories",
}

FLUX_HELMREPOSITORY = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1",
    "plural": "helmrepositories",
    "kind": "HelmRepository",
    "category": CATEGORY_SOURCES,
    "resource_type": "Helm Repositories",
}

FLUX_HELMCHART = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1",
    "plural": "helmcharts",
    "kind": "HelmChart",
    "category": CATEGORY_SOURCES,
    "resource_type": "Helm Charts",
}

FLUX_BUCKET = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1",
    "plural": "buckets",
    "kind": "Bucket",
    "category": CATEGORY_SOURCES,
    "resource_type": "Buckets",
}

FLUX_OCIREPOSITORY = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1beta2",
    "plural": "ocirepositories",
    "kind": "OCIRepository",
    "category": CATEGORY_SOURCES,
    "resource_type": "OCI Repositories",
}

FLUX_ARTIFACTGENERATOR = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1beta2",
    "plural": "artifactgenerators",
    "kind": "ArtifactGenerator",
    "category": CATEGORY_SOURCES,
    "resource_type": "Artifact Generators",
}

FLUX_EXTERNALARTIFACT = {
    "group": "source.toolkit.fluxcd.io",
    "version": "v1beta2",
    "plural": "externalartifacts",
    "kind": "ExternalArtifact",
    "category": CATEGORY_SOURCES,
    "resource_type": "External Artifacts",
}

FLUX_RESOURCESETINPUTPROVIDER = {
    "group": "fluxcd.controlplane.io",
    "version": "v1",
    "plural": "resourcesetinputproviders",
    "kind": "ResourceSetInputProvider",
    "category": CATEGORY_SOURCES,
    "resource_type": "Resource Set Input Providers",
}

# Deployments
FLUX_KUSTOMIZATION = {
    "group": "kustomize.toolkit.fluxcd.io",
    "version": "v1",
    "plural": "kustomizations",
    "kind": "Kustomization",
    "category": CATEGORY_DEPLOYMENTS,
    "resource_type": "Kustomizations",
}

FLUX_HELMRELEASE = {
    "group": "helm.toolkit.fluxcd.io",
    "version": "v2",
    "plural": "helmreleases",
    "kind": "HelmRelease",
    "category": CATEGORY_DEPLOYMENTS,
    "resource_type": "Helm Releases",
}

FLUX_FLUXINSTANCE = {
    "group": "fluxcd.controlplane.io",
    "version": "v1",
    "plural": "fluxinstances",
    "kind": "FluxInstance",
    "category": CATEGORY_DEPLOYMENTS,
    "resource_type": "Flux Instances",
}

FLUX_RESOURCESET = {
    "group": "fluxcd.controlplane.io",
    "version": "v1",
    "plural": "resourcesets",
    "kind": "ResourceSet",
    "category": CATEGORY_DEPLOYMENTS,
    "resource_type": "Resource Sets",
}

# Grouped lists
FLUX_SOURCES = [
    FLUX_ARTIFACTGENERATOR,
    FLUX_BUCKET,
    FLUX_EXTERNALARTIFACT,
    FLUX_GITREPOSITORY,
    FLUX_HELMCHART,
    FLUX_HELMREPOSITORY,
    FLUX_OCIREPOSITORY,
    FLUX_RESOURCESETINPUTPROVIDER,
]

FLUX_DEPLOYMENTS = [
    FLUX_FLUXINSTANCE,
    FLUX_HELMRELEASE,
    FLUX_KUSTOMIZATION,
    FLUX_RESOURCESET,
]

# All resources
FLUX_RESOURCES = FLUX_SOURCES + FLUX_DEPLOYMENTS

# Sensor states
STATE_READY = "ready"
STATE_NOT_READY = "not_ready"
STATE_PROGRESSING = "progressing"
STATE_SUSPENDED = "suspended"
STATE_UNKNOWN = "unknown"
STATE_DEGRADED = "degraded"

# ---------------------------------------------------------------------------
# FluxCD controller component definitions
# These are Kubernetes Deployments running in the flux-system namespace.
# ---------------------------------------------------------------------------

FLUX_CONTROLLER_NAMESPACE = "flux-system"

FLUX_CONTROLLER_NAMES = [
    "source-controller",
    "kustomize-controller",
    "helm-controller",
    "notification-controller",
    "image-reflector-controller",
    "image-automation-controller",
]
