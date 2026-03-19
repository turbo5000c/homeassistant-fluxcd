"""Tests for FluxCD integration constants."""

from __future__ import annotations

# The conftest.py sets up fluxcd_k8s as a proper package, so we can
# import const directly from it.
from fluxcd_k8s import const


class TestFluxCRDDefinitions:
    """Verify that FluxCD CRD definitions use the correct API groups and versions."""

    def test_gitrepository_crd(self):
        assert const.FLUX_GITREPOSITORY["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_GITREPOSITORY["version"] == "v1"
        assert const.FLUX_GITREPOSITORY["plural"] == "gitrepositories"
        assert const.FLUX_GITREPOSITORY["kind"] == "GitRepository"
        assert const.FLUX_GITREPOSITORY["category"] == const.CATEGORY_SOURCES

    def test_kustomization_crd(self):
        assert const.FLUX_KUSTOMIZATION["group"] == "kustomize.toolkit.fluxcd.io"
        assert const.FLUX_KUSTOMIZATION["version"] == "v1"
        assert const.FLUX_KUSTOMIZATION["plural"] == "kustomizations"
        assert const.FLUX_KUSTOMIZATION["kind"] == "Kustomization"
        assert const.FLUX_KUSTOMIZATION["category"] == const.CATEGORY_DEPLOYMENTS

    def test_helmrelease_crd(self):
        assert const.FLUX_HELMRELEASE["group"] == "helm.toolkit.fluxcd.io"
        assert const.FLUX_HELMRELEASE["version"] == "v2"
        assert const.FLUX_HELMRELEASE["plural"] == "helmreleases"
        assert const.FLUX_HELMRELEASE["kind"] == "HelmRelease"
        assert const.FLUX_HELMRELEASE["category"] == const.CATEGORY_DEPLOYMENTS

    def test_helmrepository_crd(self):
        assert const.FLUX_HELMREPOSITORY["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_HELMREPOSITORY["version"] == "v1"
        assert const.FLUX_HELMREPOSITORY["plural"] == "helmrepositories"
        assert const.FLUX_HELMREPOSITORY["kind"] == "HelmRepository"
        assert const.FLUX_HELMREPOSITORY["category"] == const.CATEGORY_SOURCES

    def test_helmchart_crd(self):
        assert const.FLUX_HELMCHART["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_HELMCHART["version"] == "v1"
        assert const.FLUX_HELMCHART["plural"] == "helmcharts"
        assert const.FLUX_HELMCHART["kind"] == "HelmChart"
        assert const.FLUX_HELMCHART["category"] == const.CATEGORY_SOURCES

    def test_bucket_crd(self):
        assert const.FLUX_BUCKET["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_BUCKET["version"] == "v1"
        assert const.FLUX_BUCKET["plural"] == "buckets"
        assert const.FLUX_BUCKET["kind"] == "Bucket"
        assert const.FLUX_BUCKET["category"] == const.CATEGORY_SOURCES

    def test_ocirepository_crd(self):
        assert const.FLUX_OCIREPOSITORY["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_OCIREPOSITORY["version"] == "v1beta2"
        assert const.FLUX_OCIREPOSITORY["plural"] == "ocirepositories"
        assert const.FLUX_OCIREPOSITORY["kind"] == "OCIRepository"
        assert const.FLUX_OCIREPOSITORY["category"] == const.CATEGORY_SOURCES

    def test_artifactgenerator_crd(self):
        assert const.FLUX_ARTIFACTGENERATOR["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_ARTIFACTGENERATOR["version"] == "v1beta2"
        assert const.FLUX_ARTIFACTGENERATOR["plural"] == "artifactgenerators"
        assert const.FLUX_ARTIFACTGENERATOR["kind"] == "ArtifactGenerator"
        assert const.FLUX_ARTIFACTGENERATOR["category"] == const.CATEGORY_SOURCES

    def test_externalartifact_crd(self):
        assert const.FLUX_EXTERNALARTIFACT["group"] == "source.toolkit.fluxcd.io"
        assert const.FLUX_EXTERNALARTIFACT["version"] == "v1beta2"
        assert const.FLUX_EXTERNALARTIFACT["plural"] == "externalartifacts"
        assert const.FLUX_EXTERNALARTIFACT["kind"] == "ExternalArtifact"
        assert const.FLUX_EXTERNALARTIFACT["category"] == const.CATEGORY_SOURCES

    def test_resourcesetinputprovider_crd(self):
        assert const.FLUX_RESOURCESETINPUTPROVIDER["group"] == "fluxcd.controlplane.io"
        assert const.FLUX_RESOURCESETINPUTPROVIDER["version"] == "v1"
        assert const.FLUX_RESOURCESETINPUTPROVIDER["plural"] == "resourcesetinputproviders"
        assert const.FLUX_RESOURCESETINPUTPROVIDER["kind"] == "ResourceSetInputProvider"
        assert const.FLUX_RESOURCESETINPUTPROVIDER["category"] == const.CATEGORY_SOURCES

    def test_fluxinstance_crd(self):
        assert const.FLUX_FLUXINSTANCE["group"] == "fluxcd.controlplane.io"
        assert const.FLUX_FLUXINSTANCE["version"] == "v1"
        assert const.FLUX_FLUXINSTANCE["plural"] == "fluxinstances"
        assert const.FLUX_FLUXINSTANCE["kind"] == "FluxInstance"
        assert const.FLUX_FLUXINSTANCE["category"] == const.CATEGORY_DEPLOYMENTS

    def test_resourceset_crd(self):
        assert const.FLUX_RESOURCESET["group"] == "fluxcd.controlplane.io"
        assert const.FLUX_RESOURCESET["version"] == "v1"
        assert const.FLUX_RESOURCESET["plural"] == "resourcesets"
        assert const.FLUX_RESOURCESET["kind"] == "ResourceSet"
        assert const.FLUX_RESOURCESET["category"] == const.CATEGORY_DEPLOYMENTS

    def test_all_resources_list(self):
        assert len(const.FLUX_RESOURCES) == 12
        kinds = [r["kind"] for r in const.FLUX_RESOURCES]
        assert "GitRepository" in kinds
        assert "Kustomization" in kinds
        assert "HelmRelease" in kinds
        assert "HelmRepository" in kinds
        assert "HelmChart" in kinds
        assert "Bucket" in kinds
        assert "OCIRepository" in kinds
        assert "ArtifactGenerator" in kinds
        assert "ExternalArtifact" in kinds
        assert "ResourceSetInputProvider" in kinds
        assert "FluxInstance" in kinds
        assert "ResourceSet" in kinds

    def test_sources_list(self):
        assert len(const.FLUX_SOURCES) == 8
        for crd in const.FLUX_SOURCES:
            assert crd["category"] == const.CATEGORY_SOURCES

    def test_deployments_list(self):
        assert len(const.FLUX_DEPLOYMENTS) == 4
        for crd in const.FLUX_DEPLOYMENTS:
            assert crd["category"] == const.CATEGORY_DEPLOYMENTS

    def test_all_resources_equals_sources_plus_deployments(self):
        assert const.FLUX_RESOURCES == const.FLUX_SOURCES + const.FLUX_DEPLOYMENTS

    def test_domain(self):
        assert const.DOMAIN == "fluxcd_k8s"

    def test_access_modes(self):
        assert const.ACCESS_MODE_IN_CLUSTER == "in_cluster"
        assert const.ACCESS_MODE_KUBECONFIG == "kubeconfig"

    def test_categories(self):
        assert const.CATEGORY_SOURCES == "Sources"
        assert const.CATEGORY_DEPLOYMENTS == "Deployments"
        assert const.CATEGORY_CONTROLLERS == "Controllers"

    def test_state_degraded(self):
        assert const.STATE_DEGRADED == "degraded"

    def test_controller_namespace(self):
        assert const.FLUX_CONTROLLER_NAMESPACE == "flux-system"

    def test_controller_names(self):
        expected = {
            "source-controller",
            "kustomize-controller",
            "helm-controller",
            "notification-controller",
            "image-reflector-controller",
            "image-automation-controller",
        }
        assert set(const.FLUX_CONTROLLER_NAMES) == expected

    def test_all_crds_have_resource_type(self):
        """Every CRD definition must include a human-readable resource_type."""
        for crd in const.FLUX_RESOURCES:
            assert "resource_type" in crd, f"{crd['kind']} missing resource_type"
            assert isinstance(crd["resource_type"], str)
            assert len(crd["resource_type"]) > 0

    def test_resource_type_values(self):
        """Verify resource_type display names for key CRDs."""
        assert const.FLUX_GITREPOSITORY["resource_type"] == "Git Repositories"
        assert const.FLUX_KUSTOMIZATION["resource_type"] == "Kustomizations"
        assert const.FLUX_HELMRELEASE["resource_type"] == "Helm Releases"
        assert const.FLUX_HELMREPOSITORY["resource_type"] == "Helm Repositories"
        assert const.FLUX_HELMCHART["resource_type"] == "Helm Charts"
        assert const.FLUX_BUCKET["resource_type"] == "Buckets"
        assert const.FLUX_OCIREPOSITORY["resource_type"] == "OCI Repositories"
        assert const.FLUX_FLUXINSTANCE["resource_type"] == "Flux Instances"
        assert const.FLUX_RESOURCESET["resource_type"] == "Resource Sets"
