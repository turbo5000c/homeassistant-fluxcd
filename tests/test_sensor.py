"""Tests for FluxCD sensor helper functions.

Covers _build_unique_id and _build_device_info which are the core functions
responsible for ensuring each FluxCD entity/device is uniquely identified in
Home Assistant.
"""

from __future__ import annotations

# conftest.py loads sensor.py via stubs so we can import the pure helpers.
from fluxcd_k8s.const import DOMAIN
from fluxcd_k8s.models import parse_flux_resource
from fluxcd_k8s.sensor import FluxCDResourceSensor, _build_device_info, _build_unique_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resource(kind: str, name: str, namespace: str = "default"):
    """Return a minimal FluxResource for the given kind/name/namespace."""
    raw = {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {},
        "status": {},
    }
    return parse_flux_resource(raw, kind)


ENTRY_ID = "test_entry_abc123"


# ---------------------------------------------------------------------------
# _build_unique_id
# ---------------------------------------------------------------------------

class TestBuildUniqueId:
    def test_includes_domain_prefix(self):
        """unique_id must start with the integration DOMAIN."""
        resource = _make_resource("HelmRelease", "traefik", "traefik")
        uid = _build_unique_id(ENTRY_ID, resource)
        assert uid.startswith(f"{DOMAIN}_"), (
            f"unique_id '{uid}' should start with '{DOMAIN}_'"
        )

    def test_includes_entry_id(self):
        resource = _make_resource("HelmRelease", "traefik", "traefik")
        uid = _build_unique_id(ENTRY_ID, resource)
        assert ENTRY_ID in uid

    def test_includes_kind(self):
        resource = _make_resource("HelmRelease", "traefik", "traefik")
        uid = _build_unique_id(ENTRY_ID, resource)
        assert "HelmRelease" in uid

    def test_includes_namespace_and_name(self):
        resource = _make_resource("Kustomization", "my-app", "my-ns")
        uid = _build_unique_id(ENTRY_ID, resource)
        assert "my-app" in uid
        assert "my-ns" in uid

    def test_different_kinds_same_namespace_name_produce_different_ids(self):
        """Core requirement: same namespace/name under different kinds must
        never share a unique_id, otherwise HA would treat them as the same
        entity and silently drop one."""
        helm_release = _make_resource("HelmRelease", "traefik", "traefik")
        helm_repo = _make_resource("HelmRepository", "traefik", "traefik")

        uid_hr = _build_unique_id(ENTRY_ID, helm_release)
        uid_repo = _build_unique_id(ENTRY_ID, helm_repo)

        assert uid_hr != uid_repo, (
            "HelmRelease and HelmRepository with same name must have different unique_ids"
        )

    def test_different_namespaces_produce_different_ids(self):
        r1 = _make_resource("Kustomization", "app", "ns-a")
        r2 = _make_resource("Kustomization", "app", "ns-b")
        assert _build_unique_id(ENTRY_ID, r1) != _build_unique_id(ENTRY_ID, r2)

    def test_different_entry_ids_produce_different_ids(self):
        resource = _make_resource("GitRepository", "flux-system", "flux-system")
        uid1 = _build_unique_id("entry-1", resource)
        uid2 = _build_unique_id("entry-2", resource)
        assert uid1 != uid2


# ---------------------------------------------------------------------------
# _build_device_info
# ---------------------------------------------------------------------------

class TestBuildDeviceInfo:
    def test_device_name_includes_namespace_and_name(self):
        resource = _make_resource("HelmRelease", "traefik", "traefik")
        info = _build_device_info(ENTRY_ID, resource)
        assert "traefik/traefik" in info["name"]

    def test_device_name_includes_resource_kind(self):
        """Device name must contain the human-readable resource kind so that
        two resources sharing the same namespace/name but of different kinds
        appear as distinct devices in the HA UI."""
        resource = _make_resource("HelmRelease", "traefik", "traefik")
        info = _build_device_info(ENTRY_ID, resource)
        # The resource_type for HelmRelease is "Helm Releases"
        assert "Helm Releases" in info["name"], (
            f"Device name '{info['name']}' should include the resource type"
        )

    def test_different_kinds_same_namespace_name_produce_different_device_names(self):
        """Core requirement: same namespace/name under different kinds must
        yield distinct device *names* so the HA UI can tell them apart."""
        helm_release = _make_resource("HelmRelease", "traefik", "traefik")
        helm_repo = _make_resource("HelmRepository", "traefik", "traefik")

        name_hr = _build_device_info(ENTRY_ID, helm_release)["name"]
        name_repo = _build_device_info(ENTRY_ID, helm_repo)["name"]

        assert name_hr != name_repo, (
            "Devices for HelmRelease and HelmRepository with the same "
            "namespace/name must have different display names"
        )

    def test_device_identifiers_differ_for_different_kinds(self):
        """Device identifiers (used by HA internally) must differ when kinds
        differ, even if namespace and name are the same."""
        r1 = _make_resource("HelmRelease", "app", "ns")
        r2 = _make_resource("HelmRepository", "app", "ns")

        ids1 = _build_device_info(ENTRY_ID, r1)["identifiers"]
        ids2 = _build_device_info(ENTRY_ID, r2)["identifiers"]
        assert ids1 != ids2

    def test_manufacturer_is_fluxcd(self):
        resource = _make_resource("GitRepository", "repo", "flux-system")
        info = _build_device_info(ENTRY_ID, resource)
        assert info["manufacturer"] == "FluxCD"

    def test_model_matches_resource_type(self):
        resource = _make_resource("Kustomization", "app", "default")
        info = _build_device_info(ENTRY_ID, resource)
        assert info["model"] == "Kustomizations"

    def test_controller_component_label(self):
        """ControllerComponent devices should say 'Flux Controller'."""
        resource = _make_resource("ControllerComponent", "source-controller", "flux-system")
        info = _build_device_info(ENTRY_ID, resource)
        assert "Flux Controller" in info["name"]
        assert info["model"] == "Flux Controller"


# ---------------------------------------------------------------------------
# FluxCDResourceSensor._resolve_relationships
# ---------------------------------------------------------------------------

class _FakeCoordinator:
    """Minimal coordinator stub for instantiating FluxCDResourceSensor."""
    last_update_success = True
    data = {}

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


class _FakeEntry:
    entry_id = ENTRY_ID


class _FakeEntityReg:
    """Entity registry that returns a pre-configured mapping."""
    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    def async_get_entity_id(self, platform, domain, unique_id):
        return self._mapping.get(unique_id)


class _FakeDevice:
    def __init__(self, device_id: str):
        self.id = device_id


class _FakeDeviceReg:
    """Device registry that returns a pre-configured mapping by identifier."""
    def __init__(self, mapping: dict[frozenset, str]):
        self._mapping = mapping

    def async_get_device(self, identifiers):
        device_id = self._mapping.get(identifiers)
        return _FakeDevice(device_id) if device_id else None


def _make_sensor(resource) -> FluxCDResourceSensor:
    """Instantiate a FluxCDResourceSensor with stub coordinator and entry."""
    coordinator = _FakeCoordinator()
    coordinator.data = {resource.kind: [resource]}
    entry = _FakeEntry()
    sensor = FluxCDResourceSensor(coordinator, entry, resource)
    # hass is normally set by HA when the entity is added; use a sentinel so
    # that the self.hass is None guard in _lookup_resource does not short-
    # circuit.  The fake registry lambdas accept and ignore the hass value.
    sensor.hass = object()
    return sensor


class TestResolveRelationships:
    """Tests for _resolve_relationships which resolves source/chart refs to
    HA entity/device IDs using the entity and device registries.
    """

    def _make_kustomization_with_source_ref(
        self,
        source_kind: str = "GitRepository",
        source_name: str = "my-repo",
        source_namespace: str = "flux-system",
    ):
        raw = {
            "metadata": {"name": "apps", "namespace": "flux-system"},
            "spec": {
                "sourceRef": {
                    "kind": source_kind,
                    "name": source_name,
                    "namespace": source_namespace,
                },
                "path": "./apps",
            },
            "status": {},
        }
        return parse_flux_resource(raw, "Kustomization", "Deployments")

    def test_resolves_source_entity_id(self):
        """When the referenced source entity exists, source_entity_id is set."""
        resource = self._make_kustomization_with_source_ref()
        sensor = _make_sensor(resource)

        target_uid = f"{DOMAIN}_{ENTRY_ID}_GitRepository_flux-system_my-repo"

        # Patch the registry helpers used inside _lookup_resource
        import fluxcd_k8s.sensor as sensor_mod
        orig_er = sensor_mod.er
        orig_dr = sensor_mod.dr

        try:
            sensor_mod.er = type("er", (), {
                "async_get": staticmethod(lambda hass: _FakeEntityReg({target_uid: "sensor.my_repo_status"}))
            })()
            sensor_mod.dr = type("dr", (), {
                "async_get": staticmethod(lambda hass: _FakeDeviceReg({}))
            })()
            result = sensor._resolve_relationships(resource)
        finally:
            sensor_mod.er = orig_er
            sensor_mod.dr = orig_dr

        assert result["source_entity_id"] == "sensor.my_repo_status"

    def test_resolves_source_device_id(self):
        """When the referenced source device exists, source_device_id is set."""
        resource = self._make_kustomization_with_source_ref()
        sensor = _make_sensor(resource)

        device_idf = frozenset({(DOMAIN, f"{ENTRY_ID}_GitRepository_flux-system_my-repo")})

        import fluxcd_k8s.sensor as sensor_mod
        orig_er = sensor_mod.er
        orig_dr = sensor_mod.dr

        try:
            sensor_mod.er = type("er", (), {
                "async_get": staticmethod(lambda hass: _FakeEntityReg({}))
            })()
            sensor_mod.dr = type("dr", (), {
                "async_get": staticmethod(lambda hass: _FakeDeviceReg({device_idf: "device-abc"}))
            })()
            result = sensor._resolve_relationships(resource)
        finally:
            sensor_mod.er = orig_er
            sensor_mod.dr = orig_dr

        assert result["source_device_id"] == "device-abc"

    def test_no_relationship_when_hass_is_none(self):
        """When hass is not yet set (entity added before hass is available),
        _lookup_resource must return (None, None) safely without crashing."""
        resource = self._make_kustomization_with_source_ref()
        sensor = _make_sensor(resource)
        sensor.hass = None  # simulate entity accessed before hass is available
        result = sensor._resolve_relationships(resource)
        assert "source_entity_id" not in result
        assert "source_device_id" not in result

    def test_no_relationship_when_resource_absent(self):
        """When the referenced resource is not registered, no rel attrs are added."""
        resource = self._make_kustomization_with_source_ref()
        sensor = _make_sensor(resource)

        import fluxcd_k8s.sensor as sensor_mod
        orig_er = sensor_mod.er
        orig_dr = sensor_mod.dr

        try:
            sensor_mod.er = type("er", (), {
                "async_get": staticmethod(lambda hass: _FakeEntityReg({}))
            })()
            sensor_mod.dr = type("dr", (), {
                "async_get": staticmethod(lambda hass: _FakeDeviceReg({}))
            })()
            result = sensor._resolve_relationships(resource)
        finally:
            sensor_mod.er = orig_er
            sensor_mod.dr = orig_dr

        assert "source_entity_id" not in result
        assert "source_device_id" not in result

    def test_no_relationship_when_no_source_ref(self):
        """Resources without source_ref_kind produce no relationship attrs."""
        resource = _make_resource("GitRepository", "my-repo", "flux-system")
        sensor = _make_sensor(resource)
        result = sensor._resolve_relationships(resource)
        assert result == {}

    def test_namespace_fallback_uses_resource_namespace(self):
        """When source_ref_namespace is empty, the resource's namespace is used."""
        raw = {
            "metadata": {"name": "apps", "namespace": "my-ns"},
            "spec": {
                "sourceRef": {
                    "kind": "GitRepository",
                    "name": "my-repo",
                    # no namespace field — should default to "my-ns"
                },
            },
            "status": {},
        }
        resource = parse_flux_resource(raw, "Kustomization", "Deployments")
        sensor = _make_sensor(resource)

        # The lookup should use "my-ns" (resource namespace) not "" (empty ref ns)
        expected_uid = f"{DOMAIN}_{ENTRY_ID}_GitRepository_my-ns_my-repo"

        import fluxcd_k8s.sensor as sensor_mod
        orig_er = sensor_mod.er
        orig_dr = sensor_mod.dr

        captured_uids: list[str] = []

        class _FakeCapturingEntityReg:
            def async_get_entity_id(self, platform, domain, unique_id):
                captured_uids.append(unique_id)
                return None

        try:
            sensor_mod.er = type("er", (), {
                "async_get": staticmethod(lambda hass: _FakeCapturingEntityReg())
            })()
            sensor_mod.dr = type("dr", (), {
                "async_get": staticmethod(lambda hass: _FakeDeviceReg({}))
            })()
            sensor._resolve_relationships(resource)
        finally:
            sensor_mod.er = orig_er
            sensor_mod.dr = orig_dr

        assert expected_uid in captured_uids

    def test_helm_release_chart_ref_resolved(self):
        """HelmRelease with chartRef should populate chart_entity_id."""
        raw = {
            "metadata": {"name": "my-release", "namespace": "default"},
            "spec": {
                "interval": "5m",
                "chartRef": {
                    "kind": "HelmChart",
                    "name": "my-helmchart",
                    "namespace": "flux-system",
                },
            },
            "status": {},
        }
        resource = parse_flux_resource(raw, "HelmRelease", "Deployments")
        sensor = _make_sensor(resource)

        chart_uid = f"{DOMAIN}_{ENTRY_ID}_HelmChart_flux-system_my-helmchart"

        import fluxcd_k8s.sensor as sensor_mod
        orig_er = sensor_mod.er
        orig_dr = sensor_mod.dr

        try:
            sensor_mod.er = type("er", (), {
                "async_get": staticmethod(lambda hass: _FakeEntityReg({chart_uid: "sensor.my_helmchart_status"}))
            })()
            sensor_mod.dr = type("dr", (), {
                "async_get": staticmethod(lambda hass: _FakeDeviceReg({}))
            })()
            result = sensor._resolve_relationships(resource)
        finally:
            sensor_mod.er = orig_er
            sensor_mod.dr = orig_dr

        assert result["chart_entity_id"] == "sensor.my_helmchart_status"
