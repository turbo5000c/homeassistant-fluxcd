"""Tests for FluxCD integration data models and parsing helpers."""

from __future__ import annotations

# Import from fluxcd_k8s.models using the package structure set up
# in conftest.py, which bypasses __init__.py (requires homeassistant).
from fluxcd_k8s.models import (
    FluxCondition,
    determine_ready_status,
    get_ready_condition,
    parse_conditions,
    parse_controller_deployment,
    parse_flux_resource,
)


# --- Fixtures ---

def _make_condition(
    cond_type: str = "Ready",
    status: str = "True",
    reason: str = "Succeeded",
    message: str = "All good",
    last_transition_time: str = "2024-01-01T00:00:00Z",
) -> dict:
    return {
        "type": cond_type,
        "status": status,
        "reason": reason,
        "message": message,
        "lastTransitionTime": last_transition_time,
    }


def _make_raw_resource(
    kind: str = "GitRepository",
    name: str = "test-repo",
    namespace: str = "flux-system",
    conditions: list[dict] | None = None,
    spec: dict | None = None,
    status_extra: dict | None = None,
) -> dict:
    status = {}
    if conditions is not None:
        status["conditions"] = conditions
    if status_extra:
        status.update(status_extra)
    return {
        "metadata": {"name": name, "namespace": namespace},
        "spec": spec or {},
        "status": status,
    }


# --- parse_conditions ---

class TestParseConditions:
    def test_empty_status(self):
        assert parse_conditions({}) == []

    def test_empty_conditions_list(self):
        assert parse_conditions({"conditions": []}) == []

    def test_single_condition(self):
        conds = parse_conditions({"conditions": [_make_condition()]})
        assert len(conds) == 1
        assert conds[0].type == "Ready"
        assert conds[0].status == "True"
        assert conds[0].reason == "Succeeded"
        assert conds[0].message == "All good"
        assert conds[0].last_transition_time == "2024-01-01T00:00:00Z"

    def test_multiple_conditions(self):
        conds = parse_conditions(
            {
                "conditions": [
                    _make_condition(cond_type="Ready", status="True"),
                    _make_condition(cond_type="Reconciling", status="False"),
                ]
            }
        )
        assert len(conds) == 2

    def test_missing_fields(self):
        """Conditions with missing fields should default to empty strings."""
        conds = parse_conditions({"conditions": [{"type": "Ready"}]})
        assert len(conds) == 1
        assert conds[0].status == ""
        assert conds[0].reason == ""
        assert conds[0].message == ""
        assert conds[0].last_transition_time == ""


# --- get_ready_condition ---

class TestGetReadyCondition:
    def test_found(self):
        conds = [
            FluxCondition("Reconciling", "False", "", "", ""),
            FluxCondition("Ready", "True", "OK", "msg", "ts"),
        ]
        ready = get_ready_condition(conds)
        assert ready is not None
        assert ready.status == "True"
        assert ready.reason == "OK"

    def test_not_found(self):
        conds = [FluxCondition("Reconciling", "False", "", "", "")]
        assert get_ready_condition(conds) is None

    def test_empty_list(self):
        assert get_ready_condition([]) is None


# --- determine_ready_status ---

class TestDetermineReadyStatus:
    def test_ready(self):
        conds = [FluxCondition("Ready", "True", "", "", "")]
        assert determine_ready_status(conds) == "ready"

    def test_not_ready(self):
        conds = [FluxCondition("Ready", "False", "", "", "")]
        assert determine_ready_status(conds) == "not_ready"

    def test_unknown_status_value(self):
        conds = [FluxCondition("Ready", "Unknown", "", "", "")]
        assert determine_ready_status(conds) == "unknown"

    def test_no_ready_condition_with_reconciling(self):
        """No Ready condition but Reconciling=True should return progressing."""
        conds = [FluxCondition("Reconciling", "True", "", "", "")]
        assert determine_ready_status(conds) == "progressing"

    def test_not_ready_with_reconciling(self):
        """Ready=False but Reconciling=True should return progressing."""
        conds = [
            FluxCondition("Ready", "False", "", "", ""),
            FluxCondition("Reconciling", "True", "", "", ""),
        ]
        assert determine_ready_status(conds) == "progressing"

    def test_no_ready_condition_no_reconciling(self):
        """No Ready and no Reconciling condition should return unknown."""
        conds = [FluxCondition("Stalled", "True", "", "", "")]
        assert determine_ready_status(conds) == "unknown"

    def test_empty_conditions(self):
        assert determine_ready_status([]) == "unknown"


# --- parse_flux_resource: GitRepository ---

class TestParseGitRepository:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="GitRepository",
            name="my-repo",
            namespace="flux-system",
            conditions=[_make_condition(status="True", reason="Succeeded", message="stored artifact")],
            spec={
                "url": "https://github.com/example/repo",
                "ref": {"branch": "main"},
                "interval": "5m",
                "suspend": False,
            },
            status_extra={
                "observedGeneration": 3,
                "artifact": {
                    "revision": "main@sha1:abc123",
                    "digest": "sha256:def456",
                },
            },
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.kind == "GitRepository"
        assert resource.name == "my-repo"
        assert resource.namespace == "flux-system"
        assert resource.category == "Sources"
        assert resource.ready_status == "ready"
        assert resource.message == "stored artifact"
        assert resource.suspend is False
        assert resource.observed_generation == 3
        # Primary attributes
        assert resource.extra_attributes["url"] == "https://github.com/example/repo"
        assert resource.extra_attributes["branch"] == "main"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["artifact_revision"] == "main@sha1:abc123"
        assert resource.diagnostic_attributes["artifact_checksum"] == "sha256:def456"
        assert resource.diagnostic_attributes["interval"] == "5m"

    def test_summary_with_branch_and_url(self):
        raw = _make_raw_resource(
            kind="GitRepository",
            name="my-repo",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "url": "https://github.com/example/repo",
                "ref": {"branch": "main"},
            },
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert "my-repo" in resource.extra_attributes["summary"]
        assert "main" in resource.extra_attributes["summary"]
        assert "https://github.com/example/repo" in resource.extra_attributes["summary"]

    def test_suspended_resource(self):
        raw = _make_raw_resource(
            spec={"suspend": True},
            conditions=[_make_condition(status="True")],
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.suspend is True
        assert resource.ready_status == "suspended"

    def test_progressing_resource(self):
        raw = _make_raw_resource(
            conditions=[
                _make_condition(cond_type="Reconciling", status="True"),
            ],
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.ready_status == "progressing"

    def test_empty_status(self):
        raw = _make_raw_resource(conditions=[])
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.ready_status == "unknown"
        assert resource.message == ""
        assert resource.reason == ""


# --- parse_flux_resource: Kustomization ---

class TestParseKustomization:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="Kustomization",
            name="my-kustomization",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "path": "./clusters/production",
                "prune": True,
                "interval": "10m",
                "sourceRef": {
                    "kind": "GitRepository",
                    "name": "my-repo",
                    "namespace": "flux-system",
                },
            },
            status_extra={
                "observedGeneration": 5,
                "lastAppliedRevision": "main@sha1:abc123",
                "lastAttemptedRevision": "main@sha1:abc123",
            },
        )
        resource = parse_flux_resource(raw, "Kustomization", "Deployments")
        assert resource.kind == "Kustomization"
        assert resource.name == "my-kustomization"
        assert resource.category == "Deployments"
        # Primary attributes
        assert resource.extra_attributes["path"] == "./clusters/production"
        assert resource.extra_attributes["prune"] is True
        assert resource.extra_attributes["source"] == "GitRepository/flux-system/my-repo"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["interval"] == "10m"
        assert resource.diagnostic_attributes["last_applied_revision"] == "main@sha1:abc123"


# --- parse_flux_resource: HelmRelease ---

class TestParseHelmRelease:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="HelmRelease",
            name="my-release",
            namespace="default",
            conditions=[_make_condition(status="True")],
            spec={
                "interval": "5m",
                "chart": {
                    "spec": {
                        "chart": "nginx",
                        "version": "1.0.0",
                        "sourceRef": {
                            "kind": "HelmRepository",
                            "name": "bitnami",
                        },
                    }
                },
            },
            status_extra={
                "observedGeneration": 2,
                "lastAppliedRevision": "1.0.0",
                "lastAttemptedRevision": "1.0.0",
                "lastReleaseRevision": 3,
            },
        )
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        assert resource.kind == "HelmRelease"
        assert resource.name == "my-release"
        assert resource.namespace == "default"
        assert resource.category == "Deployments"
        # Primary attributes
        assert resource.extra_attributes["chart_name"] == "nginx"
        assert resource.extra_attributes["chart_version"] == "1.0.0"
        assert resource.extra_attributes["source"] == "HelmRepository/bitnami"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["last_applied_revision"] == "1.0.0"
        assert resource.diagnostic_attributes["last_release_revision"] == 3

    def test_source_ref_with_namespace(self):
        raw = _make_raw_resource(
            kind="HelmRelease",
            name="my-release",
            namespace="default",
            conditions=[_make_condition(status="True")],
            spec={
                "interval": "5m",
                "chart": {
                    "spec": {
                        "chart": "nginx",
                        "version": "1.0.0",
                        "sourceRef": {
                            "kind": "HelmRepository",
                            "name": "bitnami",
                            "namespace": "flux-system",
                        },
                    }
                },
            },
            status_extra={},
        )
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        # namespace present → Kind/namespace/name
        assert resource.extra_attributes["source"] == "HelmRepository/flux-system/bitnami"

    def test_source_ref_without_namespace(self):
        raw = _make_raw_resource(
            kind="HelmRelease",
            name="my-release",
            namespace="default",
            conditions=[_make_condition(status="True")],
            spec={
                "interval": "5m",
                "chart": {
                    "spec": {
                        "chart": "nginx",
                        "version": "1.0.0",
                        "sourceRef": {
                            "kind": "HelmRepository",
                            "name": "bitnami",
                        },
                    }
                },
            },
            status_extra={},
        )
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        # namespace absent → Kind/name
        assert resource.extra_attributes["source"] == "HelmRepository/bitnami"


# --- parse_flux_resource: HelmRepository ---

class TestParseHelmRepository:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="HelmRepository",
            name="bitnami",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "url": "https://charts.bitnami.com/bitnami",
                "type": "default",
                "interval": "1h",
            },
            status_extra={
                "observedGeneration": 1,
                "artifact": {
                    "revision": "sha256:abc123",
                    "digest": "sha256:def456",
                },
            },
        )
        resource = parse_flux_resource(raw, "HelmRepository", "Sources")
        assert resource.kind == "HelmRepository"
        assert resource.category == "Sources"
        # Primary attributes
        assert resource.extra_attributes["url"] == "https://charts.bitnami.com/bitnami"
        assert resource.extra_attributes["repo_type"] == "default"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["interval"] == "1h"
        assert resource.diagnostic_attributes["artifact_revision"] == "sha256:abc123"


# --- parse_flux_resource: HelmChart ---

class TestParseHelmChart:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="HelmChart",
            name="flux-system-podinfo",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "chart": "podinfo",
                "version": "6.*",
                "interval": "5m",
                "sourceRef": {
                    "kind": "HelmRepository",
                    "name": "podinfo",
                    "namespace": "flux-system",
                },
            },
            status_extra={
                "observedGeneration": 1,
                "artifact": {
                    "revision": "6.5.0",
                    "digest": "sha256:abc123",
                },
            },
        )
        resource = parse_flux_resource(raw, "HelmChart", "Sources")
        assert resource.kind == "HelmChart"
        assert resource.category == "Sources"
        # Primary attributes
        assert resource.extra_attributes["chart"] == "podinfo"
        assert resource.extra_attributes["version"] == "6.*"
        assert resource.extra_attributes["source"] == "HelmRepository/flux-system/podinfo"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["artifact_revision"] == "6.5.0"
        assert resource.diagnostic_attributes["interval"] == "5m"

    def test_summary(self):
        raw = _make_raw_resource(
            kind="HelmChart",
            name="traefik-traefik",
            namespace="traefik",
            conditions=[_make_condition(status="True")],
            spec={
                "chart": "traefik",
                "version": "38.0.2",
                "sourceRef": {"kind": "HelmRepository", "name": "traefik"},
            },
        )
        resource = parse_flux_resource(raw, "HelmChart", "Sources")
        assert resource.extra_attributes["summary"] == "traefik 38.0.2 from HelmRepository/traefik"


# --- parse_flux_resource: Bucket ---

class TestParseBucket:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="Bucket",
            name="my-bucket",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "bucketName": "my-s3-bucket",
                "endpoint": "s3.amazonaws.com",
                "provider": "aws",
                "region": "us-east-1",
                "interval": "30m",
            },
            status_extra={
                "observedGeneration": 1,
                "artifact": {
                    "revision": "sha256:bucket123",
                    "digest": "sha256:bucketdigest",
                },
            },
        )
        resource = parse_flux_resource(raw, "Bucket", "Sources")
        assert resource.kind == "Bucket"
        assert resource.category == "Sources"
        # Primary attributes
        assert resource.extra_attributes["bucket_name"] == "my-s3-bucket"
        assert resource.extra_attributes["endpoint"] == "s3.amazonaws.com"
        assert resource.extra_attributes["provider"] == "aws"
        assert resource.extra_attributes["region"] == "us-east-1"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["artifact_revision"] == "sha256:bucket123"
        assert resource.diagnostic_attributes["interval"] == "30m"


# --- parse_flux_resource: OCIRepository ---

class TestParseOCIRepository:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="OCIRepository",
            name="my-oci",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "url": "oci://ghcr.io/my-org/my-manifests",
                "ref": {"tag": "latest", "semver": ">=1.0.0"},
                "interval": "10m",
            },
            status_extra={
                "observedGeneration": 2,
                "artifact": {
                    "revision": "latest@sha256:abc",
                    "digest": "sha256:def",
                },
            },
        )
        resource = parse_flux_resource(raw, "OCIRepository", "Sources")
        assert resource.kind == "OCIRepository"
        assert resource.category == "Sources"
        # Primary attributes
        assert resource.extra_attributes["url"] == "oci://ghcr.io/my-org/my-manifests"
        assert resource.extra_attributes["tag"] == "latest"
        assert resource.extra_attributes["semver"] == ">=1.0.0"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["artifact_revision"] == "latest@sha256:abc"
        assert resource.diagnostic_attributes["interval"] == "10m"


# --- parse_flux_resource: FluxInstance ---

class TestParseFluxInstance:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="FluxInstance",
            name="flux",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "distribution": {
                    "version": "2.x",
                    "registry": "ghcr.io/fluxcd",
                },
                "cluster": {"domain": "cluster.local"},
            },
            status_extra={
                "observedGeneration": 1,
                "lastAppliedRevision": "v2.3.0",
                "lastAttemptedRevision": "v2.3.0",
            },
        )
        resource = parse_flux_resource(raw, "FluxInstance", "Deployments")
        assert resource.kind == "FluxInstance"
        assert resource.category == "Deployments"
        # Primary attributes
        assert resource.extra_attributes["distribution_version"] == "2.x"
        assert resource.extra_attributes["distribution_registry"] == "ghcr.io/fluxcd"
        assert resource.extra_attributes["cluster_domain"] == "cluster.local"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["last_applied_revision"] == "v2.3.0"


# --- parse_flux_resource: ResourceSet ---

class TestParseResourceSet:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="ResourceSet",
            name="my-resource-set",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "inputRef": {"kind": "ConfigMap", "name": "my-inputs"},
                "interval": "5m",
            },
        )
        resource = parse_flux_resource(raw, "ResourceSet", "Deployments")
        assert resource.kind == "ResourceSet"
        assert resource.category == "Deployments"
        # Primary attributes: flattened source ref
        assert resource.extra_attributes["source"] == "ConfigMap/my-inputs"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["interval"] == "5m"


# --- parse_flux_resource: ArtifactGenerator ---

class TestParseArtifactGenerator:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="ArtifactGenerator",
            name="my-generator",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={"interval": "15m"},
            status_extra={
                "artifact": {"revision": "gen-rev", "digest": "sha256:gen"},
            },
        )
        resource = parse_flux_resource(raw, "ArtifactGenerator", "Sources")
        assert resource.kind == "ArtifactGenerator"
        assert resource.category == "Sources"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["interval"] == "15m"
        assert resource.diagnostic_attributes["artifact_revision"] == "gen-rev"


# --- parse_flux_resource: ExternalArtifact ---

class TestParseExternalArtifact:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="ExternalArtifact",
            name="my-ext-artifact",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={"url": "https://example.com/artifact.tar.gz", "interval": "1h"},
            status_extra={
                "artifact": {"revision": "ext-rev", "digest": "sha256:ext"},
            },
        )
        resource = parse_flux_resource(raw, "ExternalArtifact", "Sources")
        assert resource.kind == "ExternalArtifact"
        assert resource.category == "Sources"
        # Primary attributes
        assert resource.extra_attributes["url"] == "https://example.com/artifact.tar.gz"
        # Diagnostic attributes
        assert resource.diagnostic_attributes["interval"] == "1h"
        assert resource.diagnostic_attributes["artifact_revision"] == "ext-rev"


# --- parse_flux_resource: ResourceSetInputProvider ---

class TestParseResourceSetInputProvider:
    def test_basic_parsing(self):
        raw = _make_raw_resource(
            kind="ResourceSetInputProvider",
            name="my-provider",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "resourceRef": {
                    "kind": "ConfigMap",
                    "name": "my-config",
                    "namespace": "default",
                },
            },
        )
        resource = parse_flux_resource(raw, "ResourceSetInputProvider", "Sources")
        assert resource.kind == "ResourceSetInputProvider"
        assert resource.category == "Sources"
        # Primary attributes: flattened source ref
        assert resource.extra_attributes["source"] == "ConfigMap/default/my-config"


# --- Edge cases ---

class TestEdgeCases:
    def test_completely_empty_resource(self):
        """A resource with no metadata, spec, or status should not crash."""
        resource = parse_flux_resource({}, "GitRepository", "Sources")
        assert resource.kind == "GitRepository"
        assert resource.name == ""
        assert resource.namespace == ""
        assert resource.category == "Sources"
        assert resource.ready_status == "unknown"
        assert resource.conditions == []

    def test_unknown_kind(self):
        """An unknown kind should still parse common fields."""
        raw = _make_raw_resource(
            name="something",
            namespace="default",
            conditions=[_make_condition(status="True")],
        )
        resource = parse_flux_resource(raw, "UnknownKind", "Sources")
        assert resource.kind == "UnknownKind"
        assert resource.ready_status == "ready"
        assert resource.extra_attributes == {}

    def test_not_ready_with_message(self):
        """A not-ready resource should expose the failure message."""
        raw = _make_raw_resource(
            conditions=[
                _make_condition(
                    status="False",
                    reason="ArtifactFailed",
                    message="failed to fetch: timeout",
                )
            ]
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.ready_status == "not_ready"
        assert resource.reason == "ArtifactFailed"
        assert resource.message == "failed to fetch: timeout"

    def test_default_category_is_empty_string(self):
        """When no category is provided, it defaults to empty string."""
        raw = _make_raw_resource(conditions=[_make_condition(status="True")])
        resource = parse_flux_resource(raw, "GitRepository")
        assert resource.category == ""

    def test_suspended_overrides_ready(self):
        """Suspended flag overrides the Ready=True condition status."""
        raw = _make_raw_resource(
            spec={"suspend": True},
            conditions=[_make_condition(status="True")],
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.ready_status == "suspended"
        assert resource.suspend is True

    def test_reconcile_time_from_ready_condition(self):
        """reconcile_time should match the Ready condition's lastTransitionTime."""
        raw = _make_raw_resource(
            conditions=[
                _make_condition(
                    status="True",
                    last_transition_time="2026-02-08T01:22:37Z",
                )
            ]
        )
        resource = parse_flux_resource(raw, "GitRepository", "Sources")
        assert resource.reconcile_time == "2026-02-08T01:22:37Z"


# ---------------------------------------------------------------------------
# FluxCD controller component parsing
# ---------------------------------------------------------------------------


def _make_deployment(
    name: str = "source-controller",
    namespace: str = "flux-system",
    desired_replicas: int = 1,
    ready_replicas: int | None = 1,
    available_replicas: int | None = 1,
    observed_generation: int | None = 3,
    conditions: list[dict] | None = None,
    image: str = "ghcr.io/fluxcd/source-controller:v1.4.1",
) -> dict:
    """Build a minimal raw Kubernetes Deployment dict for tests."""
    status: dict = {"observedGeneration": observed_generation}
    if ready_replicas is not None:
        status["readyReplicas"] = ready_replicas
    if available_replicas is not None:
        status["availableReplicas"] = available_replicas
    if conditions is not None:
        status["conditions"] = conditions
    return {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "replicas": desired_replicas,
            "template": {
                "spec": {
                    "containers": [{"name": "manager", "image": image}]
                }
            },
        },
        "status": status,
    }


class TestParseControllerDeployment:
    def test_ready_controller(self):
        raw = _make_deployment(
            conditions=[
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "MinimumReplicasAvailable",
                    "message": "Deployment has minimum availability.",
                    "lastTransitionTime": "2026-03-01T10:00:00Z",
                },
                {
                    "type": "Progressing",
                    "status": "True",
                    "reason": "NewReplicaSetAvailable",
                    "message": "Deployment rolled out.",
                    "lastTransitionTime": "2026-03-01T10:00:00Z",
                },
            ]
        )
        resource = parse_controller_deployment(raw)

        assert resource.kind == "ControllerComponent"
        assert resource.name == "source-controller"
        assert resource.namespace == "flux-system"
        assert resource.category == "Controllers"
        assert resource.ready_status == "ready"
        assert resource.suspend is False
        assert resource.observed_generation == 3
        assert resource.extra_attributes["desired_replicas"] == 1
        assert resource.extra_attributes["ready_replicas"] == 1
        assert resource.extra_attributes["available_replicas"] == 1
        assert resource.extra_attributes["version"] == "v1.4.1"

    def test_version_extracted_from_image(self):
        raw = _make_deployment(image="ghcr.io/fluxcd/helm-controller:v0.37.0")
        resource = parse_controller_deployment(raw)
        assert resource.extra_attributes["version"] == "v0.37.0"

    def test_no_version_when_no_tag(self):
        raw = _make_deployment(image="ghcr.io/fluxcd/source-controller")
        resource = parse_controller_deployment(raw)
        assert "version" not in resource.extra_attributes

    def test_degraded_when_some_replicas_missing(self):
        raw = _make_deployment(
            desired_replicas=3,
            ready_replicas=1,
            available_replicas=1,
        )
        resource = parse_controller_deployment(raw)
        assert resource.ready_status == "degraded"

    def test_not_ready_when_no_replicas_available(self):
        raw = _make_deployment(
            desired_replicas=1,
            ready_replicas=0,
            available_replicas=0,
        )
        resource = parse_controller_deployment(raw)
        assert resource.ready_status == "not_ready"

    def test_progressing_during_rollout(self):
        raw = _make_deployment(
            desired_replicas=1,
            ready_replicas=0,
            available_replicas=0,
            conditions=[
                {
                    "type": "Progressing",
                    "status": "True",
                    "reason": "ReplicaSetUpdated",
                    "message": "Updating replica set.",
                    "lastTransitionTime": "2026-03-01T10:00:00Z",
                }
            ],
        )
        resource = parse_controller_deployment(raw)
        assert resource.ready_status == "progressing"

    def test_unknown_when_desired_is_zero(self):
        raw = _make_deployment(desired_replicas=0, ready_replicas=0, available_replicas=0)
        resource = parse_controller_deployment(raw)
        assert resource.ready_status == "unknown"

    def test_message_and_reason_from_available_condition(self):
        raw = _make_deployment(
            conditions=[
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "MinimumReplicasAvailable",
                    "message": "Deployment has minimum availability.",
                    "lastTransitionTime": "2026-03-14T12:00:00Z",
                }
            ]
        )
        resource = parse_controller_deployment(raw)
        assert resource.reason == "MinimumReplicasAvailable"
        assert resource.message == "Deployment has minimum availability."
        assert resource.reconcile_time == "2026-03-14T12:00:00Z"

    def test_flux_conditions_converted(self):
        raw = _make_deployment(
            conditions=[
                {
                    "type": "Available",
                    "status": "True",
                    "reason": "MinimumReplicasAvailable",
                    "message": "ok",
                    "lastTransitionTime": "2026-03-14T12:00:00Z",
                }
            ]
        )
        resource = parse_controller_deployment(raw)
        assert len(resource.conditions) == 1
        cond = resource.conditions[0]
        assert cond.type == "Available"
        assert cond.status == "True"
        assert cond.reason == "MinimumReplicasAvailable"

    def test_empty_deployment(self):
        """A completely empty deployment dict should not crash."""
        resource = parse_controller_deployment({})
        assert resource.kind == "ControllerComponent"
        assert resource.name == ""
        assert resource.namespace == ""
        # No spec.replicas → defaults to 1; no ready replicas → not_ready
        assert resource.ready_status == "not_ready"
        assert resource.conditions == []

    def test_no_containers_no_version(self):
        raw = _make_deployment()
        raw["spec"]["template"]["spec"]["containers"] = []
        resource = parse_controller_deployment(raw)
        assert "version" not in resource.extra_attributes


# ---------------------------------------------------------------------------
# Normalized source/chart ref fields
# ---------------------------------------------------------------------------

class TestNormalizedSourceRefFields:
    """Verify that normalized source_ref_* fields are present for all resource
    types that carry a sourceRef or equivalent reference.

    The human-readable 'source' attribute must be preserved alongside these
    new fields so that backward compatibility is maintained.
    """

    def test_kustomization_source_ref_fields(self):
        raw = _make_raw_resource(
            kind="Kustomization",
            name="apps",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "sourceRef": {
                    "kind": "GitRepository",
                    "name": "my-repo",
                    "namespace": "flux-system",
                },
                "path": "./apps",
                "interval": "10m",
            },
        )
        resource = parse_flux_resource(raw, "Kustomization", "Deployments")
        attrs = resource.extra_attributes
        # Human-readable attribute must still be present
        assert attrs["source"] == "GitRepository/flux-system/my-repo"
        # Normalized fields
        assert attrs["source_ref_kind"] == "GitRepository"
        assert attrs["source_ref_name"] == "my-repo"
        assert attrs["source_ref_namespace"] == "flux-system"

    def test_kustomization_source_ref_empty_when_absent(self):
        """No sourceRef → normalized fields should be empty strings."""
        raw = _make_raw_resource(kind="Kustomization", name="apps", namespace="flux-system")
        resource = parse_flux_resource(raw, "Kustomization", "Deployments")
        attrs = resource.extra_attributes
        assert attrs.get("source_ref_kind", "") == ""
        assert attrs.get("source_ref_name", "") == ""
        assert attrs.get("source_ref_namespace", "") == ""

    def test_helm_chart_source_ref_fields(self):
        raw = _make_raw_resource(
            kind="HelmChart",
            name="flux-system-podinfo",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "chart": "podinfo",
                "version": "6.*",
                "interval": "5m",
                "sourceRef": {
                    "kind": "HelmRepository",
                    "name": "podinfo",
                    "namespace": "flux-system",
                },
            },
        )
        resource = parse_flux_resource(raw, "HelmChart", "Sources")
        attrs = resource.extra_attributes
        # Human-readable attribute must still be present
        assert attrs["source"] == "HelmRepository/flux-system/podinfo"
        # Normalized fields
        assert attrs["source_ref_kind"] == "HelmRepository"
        assert attrs["source_ref_name"] == "podinfo"
        assert attrs["source_ref_namespace"] == "flux-system"

    def test_helm_release_source_ref_fields(self):
        raw = _make_raw_resource(
            kind="HelmRelease",
            name="my-release",
            namespace="default",
            conditions=[_make_condition(status="True")],
            spec={
                "interval": "5m",
                "chart": {
                    "spec": {
                        "chart": "nginx",
                        "version": "1.0.0",
                        "sourceRef": {
                            "kind": "HelmRepository",
                            "name": "bitnami",
                            "namespace": "flux-system",
                        },
                    }
                },
            },
        )
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        attrs = resource.extra_attributes
        # Human-readable attribute must still be present
        assert attrs["source"] == "HelmRepository/flux-system/bitnami"
        # Normalized fields
        assert attrs["source_ref_kind"] == "HelmRepository"
        assert attrs["source_ref_name"] == "bitnami"
        assert attrs["source_ref_namespace"] == "flux-system"
        # No chartRef → chart_ref fields should be empty
        assert attrs.get("chart_ref_kind", "") == ""
        assert attrs.get("chart_ref_name", "") == ""
        assert attrs.get("chart_ref_namespace", "") == ""

    def test_helm_release_chart_ref_fields(self):
        """HelmRelease with spec.chartRef (Flux v2.3+ style) should populate
        chart_ref_* fields and leave source_ref_* empty."""
        raw = _make_raw_resource(
            kind="HelmRelease",
            name="my-release",
            namespace="default",
            conditions=[_make_condition(status="True")],
            spec={
                "interval": "5m",
                "chartRef": {
                    "kind": "HelmChart",
                    "name": "my-helmchart",
                    "namespace": "flux-system",
                },
            },
        )
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        attrs = resource.extra_attributes
        # chart_ref fields populated
        assert attrs["chart_ref_kind"] == "HelmChart"
        assert attrs["chart_ref_name"] == "my-helmchart"
        assert attrs["chart_ref_namespace"] == "flux-system"
        # source_ref fields empty (no spec.chart.spec.sourceRef)
        assert attrs.get("source_ref_kind", "") == ""
        assert attrs.get("source_ref_name", "") == ""

    def test_resource_set_source_ref_fields(self):
        raw = _make_raw_resource(
            kind="ResourceSet",
            name="my-set",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={"inputRef": {"kind": "ResourceSetInputProvider", "name": "my-provider"}},
        )
        resource = parse_flux_resource(raw, "ResourceSet", "Deployments")
        attrs = resource.extra_attributes
        assert attrs["source"] == "ResourceSetInputProvider/my-provider"
        assert attrs["source_ref_kind"] == "ResourceSetInputProvider"
        assert attrs["source_ref_name"] == "my-provider"
        # inputRef has no namespace field
        assert attrs["source_ref_namespace"] == ""

    def test_resource_set_input_provider_source_ref_fields(self):
        raw = _make_raw_resource(
            kind="ResourceSetInputProvider",
            name="my-provider",
            namespace="flux-system",
            conditions=[_make_condition(status="True")],
            spec={
                "resourceRef": {
                    "kind": "ConfigMap",
                    "name": "my-config",
                    "namespace": "default",
                },
            },
        )
        resource = parse_flux_resource(raw, "ResourceSetInputProvider", "Sources")
        attrs = resource.extra_attributes
        assert attrs["source"] == "ConfigMap/default/my-config"
        assert attrs["source_ref_kind"] == "ConfigMap"
        assert attrs["source_ref_name"] == "my-config"
        assert attrs["source_ref_namespace"] == "default"
