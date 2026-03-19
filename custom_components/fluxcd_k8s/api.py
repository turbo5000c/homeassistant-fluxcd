"""Kubernetes API client for FluxCD resources using kubernetes-asyncio."""

from __future__ import annotations

import logging
from typing import Any

from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient, CustomObjectsApi

from .const import (
    ACCESS_MODE_IN_CLUSTER,
    FLUX_ARTIFACTGENERATOR,
    FLUX_BUCKET,
    FLUX_CONTROLLER_NAMES,
    FLUX_CONTROLLER_NAMESPACE,
    FLUX_DEPLOYMENTS,
    FLUX_EXTERNALARTIFACT,
    FLUX_FLUXINSTANCE,
    FLUX_GITREPOSITORY,
    FLUX_HELMCHART,
    FLUX_HELMRELEASE,
    FLUX_HELMREPOSITORY,
    FLUX_KUSTOMIZATION,
    FLUX_OCIREPOSITORY,
    FLUX_RESOURCES,
    FLUX_RESOURCESET,
    FLUX_RESOURCESETINPUTPROVIDER,
    FLUX_SOURCES,
)
from .models import FluxResource, parse_controller_deployment, parse_flux_resource

_LOGGER = logging.getLogger(__name__)


class FluxKubernetesClient:
    """Async client for fetching FluxCD custom resources from Kubernetes.

    Supports both in-cluster and kubeconfig-based authentication.
    """

    def __init__(
        self,
        access_mode: str,
        kubeconfig_path: str = "",
        namespace: str = "",
        label_selector: str = "",
    ) -> None:
        """Initialize the FluxCD client.

        Args:
            access_mode: Either 'in_cluster' or 'kubeconfig'.
            kubeconfig_path: Path to kubeconfig file (required if access_mode is 'kubeconfig').
            namespace: Kubernetes namespace to scope queries. Empty string means all namespaces.
            label_selector: Optional Kubernetes label selector to filter resources.
        """
        self._access_mode = access_mode
        self._kubeconfig_path = kubeconfig_path
        self._namespace = namespace
        self._label_selector = label_selector
        self._api_client: ApiClient | None = None

    async def async_init(self) -> None:
        """Initialize the Kubernetes API client.

        Loads the appropriate configuration based on access_mode and
        creates the API client instance.
        """
        if self._access_mode == ACCESS_MODE_IN_CLUSTER:
            # load_incluster_config() configures the global default client
            # settings from the pod's service account credentials
            config.load_incluster_config()
            self._api_client = ApiClient()
        else:
            self._api_client = await config.new_client_from_config(
                config_file=self._kubeconfig_path or None
            )

    async def async_close(self) -> None:
        """Close the Kubernetes API client connection."""
        if self._api_client:
            await self._api_client.close()
            self._api_client = None

    async def async_test_connection(self) -> bool:
        """Test the connection to the Kubernetes cluster.

        Returns True if the cluster is reachable, False otherwise.
        """
        if not self._api_client:
            await self.async_init()
        try:
            version_api = client.VersionApi(self._api_client)
            await version_api.get_code()
            return True
        except Exception:
            _LOGGER.exception("Failed to connect to Kubernetes cluster")
            return False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def async_get_all_flux_resources(self) -> list[FluxResource]:
        """Fetch all FluxCD resources from the Kubernetes cluster.

        Iterates over each FluxCD resource kind across both Sources and
        Deployments categories and fetches them using the CustomObjectsApi.
        Also fetches FluxCD controller Deployments from the flux-system namespace.

        Returns a list of parsed FluxResource objects.
        """
        if not self._api_client:
            await self.async_init()

        custom_api = CustomObjectsApi(self._api_client)
        all_resources: list[FluxResource] = []

        for flux_crd in FLUX_RESOURCES:
            try:
                resources = await self._async_list_flux_resource(
                    custom_api,
                    group=flux_crd["group"],
                    version=flux_crd["version"],
                    plural=flux_crd["plural"],
                    kind=flux_crd["kind"],
                    category=flux_crd["category"],
                )
                all_resources.extend(resources)
            except Exception:
                _LOGGER.warning(
                    "Failed to fetch %s resources, skipping",
                    flux_crd["kind"],
                    exc_info=True,
                )

        # Also fetch FluxCD controller deployments
        all_resources.extend(await self.async_get_flux_controllers())

        return all_resources

    # ------------------------------------------------------------------
    # Grouped fetch functions
    # ------------------------------------------------------------------

    async def async_fetch_sources(self) -> list[FluxResource]:
        """Fetch all FluxCD Source resources."""
        return await self._async_fetch_group(FLUX_SOURCES)

    async def async_fetch_deployments(self) -> list[FluxResource]:
        """Fetch all FluxCD Deployment resources."""
        return await self._async_fetch_group(FLUX_DEPLOYMENTS)

    # ------------------------------------------------------------------
    # Per-resource-type fetch functions
    # ------------------------------------------------------------------

    async def async_fetch_gitrepositories(self) -> list[FluxResource]:
        """Fetch GitRepository resources."""
        return await self._async_fetch_single_kind(FLUX_GITREPOSITORY)

    async def async_fetch_helmrepositories(self) -> list[FluxResource]:
        """Fetch HelmRepository resources."""
        return await self._async_fetch_single_kind(FLUX_HELMREPOSITORY)

    async def async_fetch_helmcharts(self) -> list[FluxResource]:
        """Fetch HelmChart resources."""
        return await self._async_fetch_single_kind(FLUX_HELMCHART)

    async def async_fetch_buckets(self) -> list[FluxResource]:
        """Fetch Bucket resources."""
        return await self._async_fetch_single_kind(FLUX_BUCKET)

    async def async_fetch_ocirepositories(self) -> list[FluxResource]:
        """Fetch OCIRepository resources."""
        return await self._async_fetch_single_kind(FLUX_OCIREPOSITORY)

    async def async_fetch_artifactgenerators(self) -> list[FluxResource]:
        """Fetch ArtifactGenerator resources."""
        return await self._async_fetch_single_kind(FLUX_ARTIFACTGENERATOR)

    async def async_fetch_externalartifacts(self) -> list[FluxResource]:
        """Fetch ExternalArtifact resources."""
        return await self._async_fetch_single_kind(FLUX_EXTERNALARTIFACT)

    async def async_fetch_resourcesetinputproviders(self) -> list[FluxResource]:
        """Fetch ResourceSetInputProvider resources."""
        return await self._async_fetch_single_kind(FLUX_RESOURCESETINPUTPROVIDER)

    async def async_fetch_kustomizations(self) -> list[FluxResource]:
        """Fetch Kustomization resources."""
        return await self._async_fetch_single_kind(FLUX_KUSTOMIZATION)

    async def async_fetch_helmreleases(self) -> list[FluxResource]:
        """Fetch HelmRelease resources."""
        return await self._async_fetch_single_kind(FLUX_HELMRELEASE)

    async def async_fetch_fluxinstances(self) -> list[FluxResource]:
        """Fetch FluxInstance resources."""
        return await self._async_fetch_single_kind(FLUX_FLUXINSTANCE)

    async def async_fetch_resourcesets(self) -> list[FluxResource]:
        """Fetch ResourceSet resources."""
        return await self._async_fetch_single_kind(FLUX_RESOURCESET)

    async def async_get_flux_controllers(self) -> list[FluxResource]:
        """Fetch FluxCD controller Deployments from the flux-system namespace.

        Queries the Kubernetes AppsV1 API for Deployments in the flux-system
        namespace and returns only the known FluxCD controller names as
        FluxResource objects with kind 'ControllerComponent'.  Missing
        controllers are handled gracefully — they simply do not appear in the
        returned list.
        """
        if not self._api_client:
            await self.async_init()

        apps_api = client.AppsV1Api(self._api_client)
        results: list[FluxResource] = []
        try:
            response = await apps_api.list_namespaced_deployment(
                namespace=FLUX_CONTROLLER_NAMESPACE
            )
            for deployment in response.items:
                dep_name = deployment.metadata.name if deployment.metadata else ""
                if dep_name not in FLUX_CONTROLLER_NAMES:
                    continue
                try:
                    raw = self._api_client.sanitize_for_serialization(deployment)
                    results.append(parse_controller_deployment(raw))
                except Exception:
                    _LOGGER.warning(
                        "Failed to parse controller deployment: %s",
                        dep_name,
                        exc_info=True,
                    )
        except Exception:
            _LOGGER.warning(
                "Failed to fetch FluxCD controller components, skipping",
                exc_info=True,
            )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _async_fetch_group(
        self, crd_list: list[dict[str, str]]
    ) -> list[FluxResource]:
        """Fetch all resources for a list of CRD definitions."""
        if not self._api_client:
            await self.async_init()

        custom_api = CustomObjectsApi(self._api_client)
        results: list[FluxResource] = []

        for flux_crd in crd_list:
            try:
                resources = await self._async_list_flux_resource(
                    custom_api,
                    group=flux_crd["group"],
                    version=flux_crd["version"],
                    plural=flux_crd["plural"],
                    kind=flux_crd["kind"],
                    category=flux_crd["category"],
                )
                results.extend(resources)
            except Exception:
                _LOGGER.warning(
                    "Failed to fetch %s resources, skipping",
                    flux_crd["kind"],
                    exc_info=True,
                )

        return results

    async def _async_fetch_single_kind(
        self, flux_crd: dict[str, str]
    ) -> list[FluxResource]:
        """Fetch resources for a single CRD definition."""
        if not self._api_client:
            await self.async_init()

        custom_api = CustomObjectsApi(self._api_client)
        try:
            return await self._async_list_flux_resource(
                custom_api,
                group=flux_crd["group"],
                version=flux_crd["version"],
                plural=flux_crd["plural"],
                kind=flux_crd["kind"],
                category=flux_crd["category"],
            )
        except Exception:
            _LOGGER.warning(
                "Failed to fetch %s resources",
                flux_crd["kind"],
                exc_info=True,
            )
            return []

    async def _async_list_flux_resource(
        self,
        custom_api: CustomObjectsApi,
        group: str,
        version: str,
        plural: str,
        kind: str,
        category: str,
    ) -> list[FluxResource]:
        """Fetch a specific FluxCD resource kind from the cluster.

        Uses list_namespaced_custom_object if a namespace is specified,
        otherwise uses list_cluster_custom_object to query all namespaces.
        """
        kwargs: dict[str, Any] = {}
        if self._label_selector:
            kwargs["label_selector"] = self._label_selector

        if self._namespace:
            # Fetch resources from a specific namespace
            response = await custom_api.list_namespaced_custom_object(
                group=group,
                version=version,
                namespace=self._namespace,
                plural=plural,
                **kwargs,
            )
        else:
            # Fetch resources from all namespaces
            response = await custom_api.list_cluster_custom_object(
                group=group,
                version=version,
                plural=plural,
                **kwargs,
            )

        items: list[dict[str, Any]] = response.get("items", [])
        resources: list[FluxResource] = []
        for item in items:
            try:
                resources.append(parse_flux_resource(item, kind, category))
            except Exception:
                _LOGGER.warning(
                    "Failed to parse %s resource: %s",
                    kind,
                    item.get("metadata", {}).get("name", "unknown"),
                    exc_info=True,
                )

        _LOGGER.debug("Fetched %d %s resources", len(resources), kind)
        return resources
