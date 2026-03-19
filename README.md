# Home Assistant integration for FluxCD GitOps status and resources

A custom Home Assistant integration that monitors **FluxCD resources in Kubernetes** using **kubernetes-asyncio**. It exposes FluxCD resource status as individual Home Assistant sensor entities, each representing a single FluxCD resource, with **category** (Sources / Deployments) and **resource type** provided as attributes.

## Features

- **Async-first design** using `kubernetes-asyncio`
- **DataUpdateCoordinator** for efficient polling
- **Config flow** for easy UI-based setup
- **Category attribute** — each resource is labeled as either *Source* or *Deployment*
- Monitors **12 FluxCD resource types** across the two categories
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

## Sensor States

Each FluxCD resource is represented as a sensor entity with one of these states:

- `ready` — The resource is reconciled and healthy
- `not_ready` — The resource has a failing condition
- `progressing` — The resource is reconciling or in the process of becoming ready
- `suspended` — The resource is intentionally paused and not reconciling
- `degraded` — The controller component is running but in a degraded or partially functional state
- `unknown` — The resource status cannot be determined

## Entity Attributes

### Common Attributes (all resource types)

- `category` — Resource category (Sources, Deployments)
- `kind` — Resource type (GitRepository, Kustomization, etc.)
- `namespace` — Kubernetes namespace
- `resource_name` — Resource name
- `suspend` — Whether the resource is suspended
- `message` — Status message from the Ready condition
- `reason` — Reason from the Ready condition
- `last_reconcile_time` — Timestamp of the last reconciliation
- `observed_generation` — Last observed generation
- `conditions` — Full list of status conditions

### GitRepository Attributes

- `url` — Git repository URL
- `branch` / `tag` / `semver` / `commit` — Git reference details
- `artifact_revision` — Last fetched artifact revision
- `interval` — Sync interval

### Kustomization Attributes

- `path` — Kustomize path
- `prune` — Whether pruning is enabled
- `interval` — Reconciliation interval
- `last_applied_revision` — Last successfully applied revision
- `source_ref_kind` / `source_ref_name` — Source reference details

### HelmRelease Attributes

- `chart_name` / `chart_version` — Helm chart details
- `source_ref_kind` / `source_ref_name` — Chart source reference
- `interval` — Reconciliation interval
- `last_applied_revision` — Last applied chart revision
- `last_attempted_revision` — Last attempted chart revision

### HelmRepository Attributes

- `url` — Helm repository URL
- `repo_type` — Repository type
- `interval` — Sync interval
- `artifact_revision` — Last fetched artifact revision

### HelmChart Attributes

- `chart` — Chart name
- `version` — Version constraint
- `source_ref_kind` / `source_ref_name` — Source reference
- `artifact_revision` — Fetched chart revision

### Bucket Attributes

- `bucket_name` — S3 bucket name
- `endpoint` — Bucket endpoint URL
- `provider` — Cloud provider (aws, gcp, generic)
- `region` — Bucket region
- `artifact_revision` — Fetched artifact revision

### OCIRepository Attributes

- `url` — OCI repository URL
- `tag` / `semver` / `digest` — OCI reference details
- `artifact_revision` — Fetched artifact revision

### FluxInstance Attributes

- `distribution_version` — Flux distribution version
- `distribution_registry` — Flux distribution registry
- `cluster_domain` — Cluster domain
- `last_applied_revision` / `last_attempted_revision` — Revision info

### ResourceSet Attributes

- `input_ref_kind` / `input_ref_name` — Input reference details
- `interval` — Reconciliation interval

### ArtifactGenerator Attributes

- `interval` — Generation interval
- `artifact_revision` — Generated artifact revision

### ExternalArtifact Attributes

- `url` — External artifact URL
- `interval` — Fetch interval
- `artifact_revision` — Fetched artifact revision

### ResourceSetInputProvider Attributes

- `resource_ref_kind` / `resource_ref_name` / `resource_ref_namespace` — Resource reference details

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

Resources are organized into two categories:

- **Sources** — Resources that define where configuration comes from (GitRepository, HelmRepository, HelmChart, Bucket, OCIRepository, ArtifactGenerator, ExternalArtifact, ResourceSetInputProvider)
- **Deployments** — Resources that apply configuration to the cluster (FluxInstance, HelmRelease, Kustomization, ResourceSet)

Each resource carries its `category` as metadata, which is exposed as a sensor attribute.

### Querying FluxCD Resources

The integration uses `kubernetes_asyncio.client.CustomObjectsApi` to explicitly fetch each FluxCD resource kind:

- **Namespaced queries**: `list_namespaced_custom_object(group, version, namespace, plural)`
- **Cluster-wide queries**: `list_cluster_custom_object(group, version, plural)`

**Grouped fetch functions:**
- `async_fetch_sources()` — Fetches all Source category resources
- `async_fetch_deployments()` — Fetches all Deployment category resources

**Per-resource-type fetch functions:**
- `async_fetch_gitrepositories()`, `async_fetch_helmrepositories()`, `async_fetch_helmcharts()`, `async_fetch_buckets()`, `async_fetch_ocirepositories()`, `async_fetch_artifactgenerators()`, `async_fetch_externalartifacts()`, `async_fetch_resourcesetinputproviders()`
- `async_fetch_kustomizations()`, `async_fetch_helmreleases()`, `async_fetch_fluxinstances()`, `async_fetch_resourcesets()`

### Entity Organization

Each FluxCD resource becomes a Home Assistant sensor entity. Entities are grouped by:

1. **Category** (Sources / Deployments)
2. **Resource type** (GitRepository, Kustomization, etc.)

Example entity names:
- `flux-system/my-repo` (Sources / Git Repositories)
- `flux-system/my-app` (Deployments / Kustomizations)
- `flux-system/flux` (Deployments / Flux Instances)

### Status Normalization

FluxCD resources store status in `status.conditions` as a list of condition objects. The integration:

1. Parses all conditions from the resource status
2. Finds the `Ready` condition
3. Maps `status: "True"` → `ready`, `status: "False"` → `not_ready`, otherwise → `unknown`
4. Extracts kind-specific attributes from `.spec` and `.status`

### Polling

A single `DataUpdateCoordinator` polls all resource kinds on the configured interval. Results are organized by kind for efficient entity lookup.

## Lovelace Dashboard Examples

> **Note:** Entity IDs are generated by Home Assistant from the device name (`{namespace}/{name}`) and the sensor name (`Status`). For example, a resource in namespace `flux-system` named `my-repo` produces entity ID `sensor.flux_system_my_repo_status`. Adjust the entity IDs below to match your actual cluster resources.

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
  - entity: sensor.flux_system_flux_system_status
    name: flux-system (GitRepository)
  - entity: sensor.flux_system_flux_system_artifact_revision
    name: Artifact Revision
  - entity: sensor.flux_system_flux_system_interval
    name: Sync Interval
  - entity: sensor.flux_system_bitnami_status
    name: bitnami (HelmRepository)
  - entity: sensor.flux_system_bitnami_artifact_revision
    name: Artifact Revision
```

> **Tip:** Diagnostic sensor entity IDs follow the pattern `sensor.{namespace}_{name}_{attribute}`. For example, the `Artifact Revision` diagnostic sensor for `flux-system/flux-system` becomes `sensor.flux_system_flux_system_artifact_revision`.

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

> **Note:** Controller Kustomization entity IDs depend on how Flux is installed in your cluster. If Flux was bootstrapped with the default names, the entities will follow the `sensor.flux_system_{controller_name}_status` pattern shown above.
>
> To find your actual controller names, run:
> ```bash
> kubectl get kustomizations -n flux-system
> ```
> Convert each name to a sensor entity ID by replacing hyphens and slashes with underscores and appending `_status`. For example, a Kustomization named `helm-controller` in `flux-system` becomes `sensor.flux_system_helm_controller_status`.

## Requirements

- Home Assistant 2024.9.1+
- Python 3.11+
- `kubernetes-asyncio` (installed automatically)
- Kubernetes cluster with FluxCD installed
- Appropriate RBAC permissions (see above)

## License

This project is provided as-is for monitoring FluxCD resources in Home Assistant.
