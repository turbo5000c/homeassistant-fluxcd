# Home Assistant integration for FluxCD GitOps status and resources

A custom Home Assistant integration that monitors **FluxCD resources in Kubernetes** using **kubernetes-asyncio**. It exposes FluxCD resource status as Home Assistant sensor entities, each appearing as its own top-level device in the HA device registry.

## Companion Lovelace Card

The [**fluxcd-topology-card**](https://github.com/dawg-io/fluxcd-topology-card) is an optional companion custom card for Home Assistant dashboards. It visualizes the relationships between FluxCD resources (GitRepositories, HelmRepositories, HelmCharts, HelmReleases, Kustomizations, and more) as an interactive topology graph directly in your Lovelace UI.

It is built to work alongside this integration and enhances the monitoring experience by providing a graphical overview of your FluxCD resource dependencies — but it is entirely optional and not required for this integration to function.

👉 [https://github.com/dawg-io/fluxcd-topology-card](https://github.com/dawg-io/fluxcd-topology-card)

## Features

- **Async-first design** using `kubernetes-asyncio`
- **DataUpdateCoordinator** for efficient polling
- **Config flow** for easy UI-based setup
- Monitors **12 FluxCD CRD resource types** across Sources and Deployments
- **Controller monitoring** — monitors FluxCD controller Deployments (source-controller, kustomize-controller, helm-controller, notification-controller, image-reflector-controller, image-automation-controller)
- Supports **in-cluster** and **kubeconfig** authentication
- **Namespace scoping** — monitor a single namespace or all namespaces
- **Label selector** filtering for targeted monitoring
- **Configurable scan interval**
- **Grouped and per-resource-type fetch functions** for flexible querying

## Resource Categories

### Sources

| Resource | API Group / Version | Purpose |
|---|---|---|
| ArtifactGenerator | `source.toolkit.fluxcd.io/v1beta2` | Generate artifacts from various inputs |
| Bucket | `source.toolkit.fluxcd.io/v1` | S3-compatible bucket source |
| ExternalArtifact | `source.toolkit.fluxcd.io/v1beta2` | External artifact reference |
| GitRepository | `source.toolkit.fluxcd.io/v1` | Source sync status, last fetched commit |
| HelmChart | `source.toolkit.fluxcd.io/v1` | Helm chart source tracking |
| HelmRepository | `source.toolkit.fluxcd.io/v1` | Helm repo sync status |
| OCIRepository | `source.toolkit.fluxcd.io/v1beta2` | OCI artifact source |
| ResourceSetInputProvider | `fluxcd.controlplane.io/v1` | Input provider for ResourceSets |

### Deployments

| Resource | API Group / Version | Purpose |
|---|---|---|
| FluxInstance | `fluxcd.controlplane.io/v1` | Flux operator instance status |
| HelmRelease | `helm.toolkit.fluxcd.io/v2` | Helm chart deployment status |
| Kustomization | `kustomize.toolkit.fluxcd.io/v1` | Deployment reconcile status, last applied revision |
| ResourceSet | `fluxcd.controlplane.io/v1` | Templated resource deployment |

### Controllers

| Resource | Source | Purpose |
|---|---|---|
| ControllerComponent | Kubernetes Deployment (`apps/v1`) | FluxCD controller Deployment health (source-controller, kustomize-controller, helm-controller, notification-controller, image-reflector-controller, image-automation-controller) |

## Sensor States

Each FluxCD resource is represented as a sensor entity with one of these states:

- `ready` — The resource is reconciled and healthy
- `not_ready` — The resource has a failing condition
- `progressing` — The resource is actively reconciling (Reconciling condition is True)
- `suspended` — The resource is suspended (`spec.suspend: true`)
- `degraded` — Some but not all controller replicas are available (ControllerComponent only)
- `unknown` — The resource status cannot be determined

## Entity Attributes and Diagnostic Sensors

Each FluxCD resource has a primary **Status** sensor with state attributes, plus several **Diagnostic** sensors that surface low-level detail. Diagnostic sensors appear in the "Diagnostic" section of the HA device page.

### Common Attributes (all resource types — primary Status sensor)

- `category` — Resource category (`sources`, `deployments`, `controllers`)
- `kind` — Resource type (GitRepository, Kustomization, etc.)
- `namespace` — Kubernetes namespace
- `resource_name` — Resource name
- `suspended` — Whether the resource is suspended
- `message` — Status message from the Ready condition
- `reason` — Reason from the Ready condition
- `reconcile_time` — Timestamp of the last reconciliation

### Common Diagnostic Sensors (all resource types)

- `Ready Condition` — Boolean value of the `Ready` condition
- `Observed Generation` — Last observed generation from status

### GitRepository

**Primary attributes:**
- `url` — Git repository URL
- `branch` / `tag` / `semver` / `commit` — Git reference details
- `summary` — Human-readable summary (e.g., `"my-repo main from https://github.com/org/repo"`)

**Diagnostic sensors:**
- `Interval` — Sync interval
- `Artifact Revision` — Last fetched artifact revision

### Kustomization

**Primary attributes:**
- `path` — Kustomize path
- `prune` — Whether pruning is enabled
- `source` — Formatted source reference (e.g., `"GitRepository/flux-system/my-repo"`)
- `source_ref_kind` / `source_ref_name` / `source_ref_namespace` — Source reference details
- `source_entity_id` / `source_device_id` — HA entity/device IDs for the linked source (resolved at runtime)
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Reconciliation interval
- `Last Applied Revision` — Last successfully applied revision

### HelmRelease

**Primary attributes:**
- `chart_name` / `chart_version` — Helm chart details
- `source` — Formatted source reference
- `source_ref_kind` / `source_ref_name` / `source_ref_namespace` — Chart source reference (for inline `spec.chart.spec.sourceRef`)
- `chart_ref_kind` / `chart_ref_name` / `chart_ref_namespace` — Direct HelmChart reference (Flux v2.3+ `spec.chartRef`)
- `source_entity_id` / `source_device_id` — Resolved HA entity/device for the source
- `chart_entity_id` / `chart_device_id` — Resolved HA entity/device for the HelmChart (when `chart_ref_kind` is set)
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Reconciliation interval
- `Last Applied Revision` — Last applied chart revision

### HelmRepository

**Primary attributes:**
- `url` — Helm repository URL
- `repo_type` — Repository type (default, oci)
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Sync interval
- `Artifact Revision` — Last fetched artifact revision

### HelmChart

**Primary attributes:**
- `chart` — Chart name
- `version` — Version constraint
- `source` — Formatted source reference
- `source_ref_kind` / `source_ref_name` / `source_ref_namespace` — Source reference
- `source_entity_id` / `source_device_id` — Resolved HA entity/device for the source
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Sync interval
- `Artifact Revision` — Fetched chart revision

### Bucket

**Primary attributes:**
- `bucket_name` — S3 bucket name
- `endpoint` — Bucket endpoint URL
- `provider` — Cloud provider (aws, gcp, generic)
- `region` — Bucket region
- `prefix` — Object prefix filter
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Sync interval
- `Artifact Revision` — Fetched artifact revision

### OCIRepository

**Primary attributes:**
- `url` — OCI repository URL
- `tag` / `semver` / `digest` — OCI reference details
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Sync interval
- `Artifact Revision` — Fetched artifact revision

### FluxInstance

**Primary attributes:**
- `distribution_version` — Flux distribution version
- `distribution_registry` — Flux distribution registry
- `cluster_domain` — Cluster domain
- `summary` — Human-readable summary (e.g., `"FluxCD v2.3.0"`)

**Diagnostic sensors:**
- `Last Applied Revision` — Last successfully applied revision

### ResourceSet

**Primary attributes:**
- `source` — Formatted input reference
- `source_ref_kind` / `source_ref_name` — Input reference details
- `source_entity_id` / `source_device_id` — Resolved HA entity/device for the input provider
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Reconciliation interval

### ArtifactGenerator

**Diagnostic sensors:**
- `Interval` — Generation interval
- `Artifact Revision` — Generated artifact revision

### ExternalArtifact

**Primary attributes:**
- `url` — External artifact URL
- `summary` — Human-readable summary

**Diagnostic sensors:**
- `Interval` — Fetch interval
- `Artifact Revision` — Fetched artifact revision

### ResourceSetInputProvider

**Primary attributes:**
- `source` — Formatted resource reference
- `summary` — Human-readable summary derived from the source
- `source_ref_kind` / `source_ref_name` / `source_ref_namespace` — Resource reference details
- `source_entity_id` / `source_device_id` — Resolved HA entity/device for the referenced resource

### ControllerComponent

FluxCD controller Deployments (e.g., source-controller, kustomize-controller) are monitored as `ControllerComponent` resources in the `controllers` category.

**Primary attributes:**
- `desired_replicas` — Expected number of replicas
- `ready_replicas` — Currently ready replicas
- `available_replicas` — Currently available replicas
- `version` — Container image tag (e.g., `v2.3.0`)

**Diagnostic sensors:**
- `Ready Condition` — Boolean value of the `Ready` condition (may be `unknown` if the Deployment only exposes `Available`/`Progressing` conditions)
- `Observed Generation` — Last observed generation
- `Desired Replicas` — Expected replica count
- `Ready Replicas` — Ready replica count
- `Available Replicas` — Available replica count

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Install the "FluxCD" integration
3. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/fluxcd_k8s` directory to your Home Assistant `custom_components` directory:
   ```bash
   cp -r custom_components/fluxcd_k8s /path/to/homeassistant/custom_components/
   ```
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **FluxCD**
4. Configure the following:
   - **Access Mode**: Select `In-Cluster` if Home Assistant runs inside Kubernetes, or `Kubeconfig File` for external access
   - **Kubeconfig Path**: Path to your kubeconfig file (only needed for Kubeconfig mode; leave empty for the default `~/.kube/config`)
   - **Namespace**: Kubernetes namespace to monitor (leave empty for all namespaces)
   - **Scan Interval**: How often to poll FluxCD resources (in seconds, minimum 10, default 60)
   - **Label Selector**: Optional Kubernetes label selector to filter resources

## Kubernetes RBAC

The integration requires read-only access to FluxCD custom resources. Apply the included RBAC manifest:

```bash
kubectl apply -f rbac.yaml
```

This creates a `ClusterRole` with `get`, `list`, and `watch` permissions on:
- `gitrepositories`, `helmrepositories`, `helmcharts`, `buckets`, `ocirepositories`, `artifactgenerators`, `externalartifacts` (`source.toolkit.fluxcd.io`)
- `kustomizations` (`kustomize.toolkit.fluxcd.io`)
- `helmreleases` (`helm.toolkit.fluxcd.io`)
- `fluxinstances`, `resourcesets`, `resourcesetinputproviders` (`fluxcd.controlplane.io`)

Edit the `ClusterRoleBinding` subject to match your Home Assistant service account.

> **Note:** Controller component monitoring (source-controller, kustomize-controller, etc.)
> requires `get` and `list` access to `deployments` in the `apps` API group for the
> `flux-system` namespace. If your service account does not have this permission the
> integration will still start, but controller entities will not appear. Add the following
> rule to the ClusterRole in `rbac.yaml` if you want controller monitoring:
>
> ```yaml
> - apiGroups:
>     - apps
>   resources:
>     - deployments
>   verbs:
>     - get
>     - list
> ```

## Project Structure

```
custom_components/fluxcd_k8s/
├── __init__.py        # Integration setup and teardown
├── manifest.json      # Integration metadata and requirements
├── const.py           # Constants, CRD definitions, and category groupings
├── config_flow.py     # Configuration UI flow
├── coordinator.py     # DataUpdateCoordinator for polling
├── api.py             # Kubernetes API client with grouped/per-type fetch functions
├── models.py          # Data models and kind-specific parsing helpers
├── sensor.py          # Sensor entity platform
├── strings.json       # UI strings
└── translations/
    └── en.json        # English translations
```

## How It Works

### Resource Grouping by Category

Resources carry a `category` attribute that is exposed as a sensor attribute:

- **Sources** — Resources that define where configuration comes from (GitRepository, HelmRepository, HelmChart, Bucket, OCIRepository, ArtifactGenerator, ExternalArtifact, ResourceSetInputProvider)
- **Deployments** — Resources that apply configuration to the cluster (FluxInstance, HelmRelease, Kustomization, ResourceSet)
- **Controllers** — FluxCD controller Deployments (source-controller, kustomize-controller, helm-controller, notification-controller, image-reflector-controller, image-automation-controller)

### Querying FluxCD Resources

The integration uses `kubernetes_asyncio.client.CustomObjectsApi` to explicitly fetch each FluxCD resource kind:

- **Namespaced queries**: `list_namespaced_custom_object(group, version, namespace, plural)`
- **Cluster-wide queries**: `list_cluster_custom_object(group, version, plural)`
- **Controller Deployments**: `AppsV1Api.list_namespaced_deployment(namespace="flux-system")`

**Grouped fetch functions:**
- `async_fetch_sources()` — Fetches all Source category resources
- `async_fetch_deployments()` — Fetches all Deployment category resources

**Per-resource-type fetch functions:**
- `async_fetch_gitrepositories()`, `async_fetch_helmrepositories()`, `async_fetch_helmcharts()`, `async_fetch_buckets()`, `async_fetch_ocirepositories()`, `async_fetch_artifactgenerators()`, `async_fetch_externalartifacts()`, `async_fetch_resourcesetinputproviders()`
- `async_fetch_kustomizations()`, `async_fetch_helmreleases()`, `async_fetch_fluxinstances()`, `async_fetch_resourcesets()`

### Entity Organization

Each FluxCD resource becomes its own top-level **device** in Home Assistant. Each device exposes:
- A primary **Status** sensor (the resource's ready state)
- Several **Diagnostic** sensors (interval, revision, replica counts, etc.)

Device names use the format `{namespace}/{name} ({resource type})`. Including the resource type prevents display name collisions when multiple resource kinds share the same namespace and name (e.g., a HelmRelease and a HelmRepository both named `traefik/traefik`).

Example device names:
- `flux-system/my-repo (Git Repositories)`
- `flux-system/my-app (Kustomizations)`
- `flux-system/flux (Flux Instances)`
- `flux-system/source-controller (Flux Controller)`

### Status Normalization

FluxCD resources store status in `status.conditions` as a list of condition objects. The integration:

1. Parses all conditions from the resource status
2. Finds the `Ready` condition
3. Checks for an active `Reconciling` condition to detect `progressing` state
4. Maps `status: "True"` → `ready`, `status: "False"` → `not_ready`, otherwise → `unknown`
5. Overrides with `suspended` when `spec.suspend: true`
6. Extracts kind-specific attributes from `.spec` and `.status`

For controller Deployments, status is derived from replica counts and the Deployment's `Available`/`Progressing` conditions.

### Polling

A single `DataUpdateCoordinator` polls all resource kinds on the configured interval. Results are organized by kind for efficient entity lookup.

## Lovelace Dashboard Examples

> **Note:** Entity IDs are generated by Home Assistant from the device name
> (`{namespace}/{name} ({resource type})`) and the sensor name (`Status`).
> For example, a GitRepository in namespace `flux-system` named `my-repo` produces
> entity ID `sensor.flux_system_my_repo_git_repositories_status`. A Kustomization
> with the same namespace/name produces `sensor.flux_system_my_repo_kustomizations_status`.
> Adjust the entity IDs below to match your actual cluster resources — you can find
> the exact IDs in **Settings → Devices & Services → FluxCD**.

### Glance Card — Quick Status Overview

Show the ready state of several FluxCD resources at a glance:

```yaml
type: glance
title: FluxCD Status
entities:
  - entity: sensor.flux_system_flux_system_status
    name: flux-system
  - entity: sensor.flux_system_bitnami_status
    name: bitnami
  - entity: sensor.default_podinfo_status
    name: podinfo
  - entity: sensor.default_apps_status
    name: apps
```

### Entities Card — Deployment Details

List deployment resources with their current state and key attributes:

```yaml
type: entities
title: FluxCD Deployments
entities:
  - entity: sensor.flux_system_flux_system_status
    name: flux-system (Kustomization)
  - entity: sensor.default_apps_status
    name: apps (Kustomization)
  - entity: sensor.default_podinfo_status
    name: podinfo (HelmRelease)
  - entity: sensor.flux_system_flux_status
    name: flux (FluxInstance)
```

### Entity Filter Card — Unhealthy Resources Only

Display a card only when one or more resources are in the `not_ready` state:

```yaml
type: entity-filter
title: FluxCD Issues
entities:
  - sensor.flux_system_flux_system_status
  - sensor.flux_system_bitnami_status
  - sensor.default_apps_status
  - sensor.default_podinfo_status
state_filter:
  - not_ready
card:
  type: entities
  title: Unhealthy FluxCD Resources
show_empty: false
```

### Conditional Card — Alert on Failure

Show a detailed alert card only when a specific resource is not ready:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.flux_system_flux_system_status
    state: not_ready
card:
  type: entities
  title: "⚠️ FluxCD Alert: flux-system/flux-system"
  entities:
    - entity: sensor.flux_system_flux_system_status
      name: Status
    - type: attribute
      entity: sensor.flux_system_flux_system_status
      attribute: message
      name: Message
    - type: attribute
      entity: sensor.flux_system_flux_system_status
      attribute: reason
      name: Reason
    - type: attribute
      entity: sensor.flux_system_flux_system_status
      attribute: reconcile_time
      name: Last Reconcile
```

### Markdown Card — Formatted Status Table

Render a dynamic Markdown table with the current status of your resources using HA templates:

```yaml
type: markdown
title: FluxCD Summary
content: |
  | Resource | Kind | Status |
  |----------|------|--------|
  | flux-system/flux-system | Kustomization | {{ states('sensor.flux_system_flux_system_status') }} |
  | flux-system/bitnami | HelmRepository | {{ states('sensor.flux_system_bitnami_status') }} |
  | default/apps | Kustomization | {{ states('sensor.default_apps_status') }} |
  | default/podinfo | HelmRelease | {{ states('sensor.default_podinfo_status') }} |
```

### Entities Card — GitRepository with Revision

Show the last fetched artifact revision alongside the ready state for source resources:

```yaml
type: entities
title: FluxCD Sources
entities:
  - entity: sensor.flux_system_flux_system_git_repositories_status
    name: flux-system (GitRepository)
  - entity: sensor.flux_system_flux_system_git_repositories_artifact_revision
    name: Artifact Revision
  - entity: sensor.flux_system_flux_system_git_repositories_interval
    name: Sync Interval
  - entity: sensor.flux_system_bitnami_helm_repositories_status
    name: bitnami (HelmRepository)
  - entity: sensor.flux_system_bitnami_helm_repositories_artifact_revision
    name: Artifact Revision
```

> **Tip:** Diagnostic sensor entity IDs follow the pattern `sensor.{namespace}_{name}_{resource_type}_{attribute}`. For example, the `Artifact Revision` diagnostic sensor for the GitRepository `flux-system/flux-system` becomes `sensor.flux_system_flux_system_git_repositories_artifact_revision`.

### FluxCD Component Health Card

Monitor the health of the core Flux controllers in your cluster. Flux installs controllers such as `source-controller`, `kustomize-controller`, `helm-controller`, and `notification-controller` as Kustomizations in the `flux-system` namespace. These appear as entities in this integration.

The `FluxInstance` entity (if you use the [flux-operator](https://github.com/controlplaneio-fluxcd/flux-operator)) exposes the overall Flux distribution version and last applied revision.

Use a **Markdown card** with Jinja2 templates to render a status table with color-coded icons:

```yaml
type: markdown
title: FluxCD Component Health
content: >
  ## FluxCD Controllers {% set ns = namespace(all_ready=true) %} {% set
  resources = [
    ('source-controller',       states('sensor.flux_system_source_controller_status')),
    ('kustomize-controller',    states('sensor.flux_system_kustomize_controller_status')),
    ('helm-controller',         states('sensor.flux_system_helm_controller_status')),
    ('notification-controller', states('sensor.flux_system_notification_controller_status')),
  ] %}

  | Controller | Status |

  |-----------|--------|

  {% for name, state in resources %}{% if state == 'ready' %} | {{ name }} | ✅
  Ready |

  {% elif state == 'not_ready' %}| {{ name }} | ❌ Error |{% set ns.all_ready =
  false %} {% elif state == 'progressing' %}| {{ name }} | ⏳ Reconciling | {%
  elif state == 'suspended' %}| {{ name }} | ⏸ Suspended | {% else %}| {{ name
  }} | ❓ Unknown | {% endif %}{% endfor %}

  {% if ns.all_ready %}✅ All controllers healthy{% else %}⚠️ One or more
  controllers need attention{% endif %}
```

For a card that shows **last reconcile time and error messages** for each controller, combine status and attribute rows in an entities card:

```yaml
type: entities
title: FluxCD Controllers
entities:
  - entity: sensor.flux_system_source_controller_status
    name: Source Controller
  - type: attribute
    entity: sensor.flux_system_source_controller_status
    attribute: reconcile_time
    name: "  Last Reconcile"
  - type: attribute
    entity: sensor.flux_system_source_controller_status
    attribute: message
    name: "  Message"
  - type: divider
  - entity: sensor.flux_system_kustomize_controller_status
    name: Kustomize Controller
  - type: attribute
    entity: sensor.flux_system_kustomize_controller_status
    attribute: reconcile_time
    name: "  Last Reconcile"
  - type: attribute
    entity: sensor.flux_system_kustomize_controller_status
    attribute: message
    name: "  Message"
  - type: divider
  - entity: sensor.flux_system_helm_controller_status
    name: Helm Controller
  - type: attribute
    entity: sensor.flux_system_helm_controller_status
    attribute: reconcile_time
    name: "  Last Reconcile"
  - type: attribute
    entity: sensor.flux_system_helm_controller_status
    attribute: message
    name: "  Message"
  - type: divider
  - entity: sensor.flux_system_notification_controller_status
    name: Notification Controller
  - type: attribute
    entity: sensor.flux_system_notification_controller_status
    attribute: reconcile_time
    name: "  Last Reconcile"
  - type: attribute
    entity: sensor.flux_system_notification_controller_status
    attribute: message
    name: "  Message"
```

To also show the overall **FluxInstance** status (Flux Operator distribution version and last applied revision):

```yaml
type: entities
title: Flux Operator Instance
entities:
  - entity: sensor.flux_system_flux_status
    name: Flux Instance
  - type: attribute
    entity: sensor.flux_system_flux_status
    attribute: distribution_version
    name: Distribution Version
  - entity: sensor.flux_system_flux_last_applied_revision
    name: Last Applied Revision
  - type: attribute
    entity: sensor.flux_system_flux_status
    attribute: reconcile_time
    name: Last Reconcile
  - type: attribute
    entity: sensor.flux_system_flux_status
    attribute: message
    name: Message
```

> **Note:** Controller Kustomization entity IDs depend on how Flux is installed in your cluster. If Flux was bootstrapped with the default names, the entities will follow the `sensor.flux_system_{controller_name}_kustomizations_status` pattern.
>
> Controller **Deployment** entities (ControllerComponent kind) follow the pattern `sensor.flux_system_{controller_name}_flux_controller_status`.
>
> To find your actual controller names, run:
> ```bash
> kubectl get kustomizations -n flux-system
> ```
> Convert each name to a sensor entity ID by replacing hyphens and slashes with underscores, appending the resource type slug, and then `_status`. For example, a Kustomization named `helm-controller` in `flux-system` becomes `sensor.flux_system_helm_controller_kustomizations_status`.

## Requirements

- Home Assistant 2024.9.1+
- Python 3.11+
- `kubernetes-asyncio` (installed automatically)
- Kubernetes cluster with FluxCD installed
- Appropriate RBAC permissions (see above)

## License

This project is provided as-is for monitoring FluxCD resources in Home Assistant.
