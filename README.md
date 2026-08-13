# Home Assistant integration for FluxCD GitOps status and resources

A custom Home Assistant integration that monitors **FluxCD resources in Kubernetes** using **kubernetes-asyncio**. It exposes FluxCD resource status as Home Assistant sensor entities, each appearing as its own top-level device in the HA device registry.

## Contents

- [Installation](#installation)
  - [Before you start](#before-you-start)
  - [Step 1 — Install the integration](#step-1--install-the-integration)
  - [Step 2 — Choose how Home Assistant reaches your cluster](#step-2--choose-how-home-assistant-reaches-your-cluster)
  - [Step 3 — Apply the Kubernetes RBAC](#step-3--apply-the-kubernetes-rbac)
  - [Step 4 — Add the integration in Home Assistant](#step-4--add-the-integration-in-home-assistant)
  - [Troubleshooting](#troubleshooting)
- [Features](#features)
- [Companion Lovelace Card](#companion-lovelace-card)
- [Resource Categories](#resource-categories)
- [Sensor States](#sensor-states)
- [Entity Attributes and Diagnostic Sensors](#entity-attributes-and-diagnostic-sensors)
- [How It Works](#how-it-works)
- [Lovelace Dashboard Examples](#lovelace-dashboard-examples)
- [Project Structure](#project-structure)
- [License](#license)

---

## Installation

### Before you start

| Requirement | Notes |
|---|---|
| Home Assistant 2024.9.1 or newer | Any install type (OS, Container, Supervised, Core) |
| Python 3.11+ | Already bundled with supported Home Assistant versions |
| A Kubernetes cluster running FluxCD | Flux v2 CRDs; the Flux Operator is optional |
| Network access to the Kubernetes API server | From the machine running Home Assistant |
| `kubernetes-asyncio` | Installed automatically by Home Assistant |

### Step 1 — Install the integration

#### HACS (recommended)

1. In HACS, open the three-dot menu → **Custom repositories**
2. Add this repository with the category **Integration**
3. Search for **FluxCD** in HACS and install it
4. Restart Home Assistant

#### Manual

1. Copy the `custom_components/fluxcd_k8s` directory into your Home Assistant `custom_components` directory (next to `configuration.yaml`):
   ```bash
   cp -r custom_components/fluxcd_k8s /path/to/homeassistant/custom_components/
   ```
2. Restart Home Assistant

### Step 2 — Choose how Home Assistant reaches your cluster

| Access mode | Use when | What you need |
|---|---|---|
| **In-Cluster** | Home Assistant runs as a pod inside the cluster | Nothing — the pod's service account is used automatically |
| **Kubeconfig File** | Home Assistant runs outside the cluster (HA OS, Container, Supervised, Core) | A kubeconfig file that Home Assistant can read |

**In-Cluster** mode needs no further file setup — skip to [Step 3](#step-3--apply-the-kubernetes-rbac).

#### Where to put the kubeconfig file

Copy your kubeconfig into the Home Assistant **config directory** (the folder that holds `configuration.yaml`, usually `/config`) and name it `kubeconfig`:

```bash
# Docker / HA Container install, from a machine that has cluster access:
docker cp ~/.kube/config homeassistant:/config/kubeconfig

# HA OS / Supervised: copy it in with the Samba, SSH, Terminal,
# or File Editor add-on instead — the destination is the same.
```

Then either **leave the Kubeconfig Path field empty** (the file is found automatically) or set it to `/config/kubeconfig`.

> **Why the config directory?** On HA OS, Supervised, and Container installs the home directory (`~`, which is `/root`) lives inside the container image, so anything stored there is lost the next time the container is recreated or Home Assistant is updated. The config directory is a mounted volume and survives.

#### What the Kubeconfig Path field accepts

| Value | Result |
|---|---|
| _(empty)_ | The default locations below are searched |
| `/config/kubeconfig` | That exact file is used |
| `~/.kube/config` | `~` is expanded to the home directory of the user running Home Assistant |
| `$MY_DIR/kubeconfig` | Environment variables are expanded |
| `/config/.kube` | A directory — it is searched for `config`, `kubeconfig`, `kubeconfig.yaml`, `kubeconfig.yml` (also inside a `.kube` subdirectory) |
| `/config/a.yaml:/config/b.yaml` | Multiple `:`-separated files, merged the same way the `KUBECONFIG` environment variable works |

#### Default search order (empty path)

1. Every path listed in the `KUBECONFIG` environment variable
2. `<config dir>/.kube/` then `<config dir>/` — e.g. `/config/.kube/`, `/config/`
3. `~/.kube/` then `~/`
4. `/config/.kube/`, `/config/`, `/root/.kube/`

In each directory the first match of `config`, `kubeconfig`, `kubeconfig.yaml`, or `kubeconfig.yml` is used.

#### Kubeconfig requirements

- Service account tokens, client certificates, and basic auth all work out of the box.
- `exec:` credential plugins (`aws eks get-token`, `gke-gcloud-auth-plugin`, and similar) only work if that binary exists **inside** the Home Assistant container — usually it does not. Use a service account token instead (see the next step).
- The API server address must be reachable from Home Assistant, and its certificate must validate — embed `certificate-authority-data` in the kubeconfig if you use a private CA.

### Step 3 — Apply the Kubernetes RBAC

The integration only needs read-only access to FluxCD resources. Apply the included manifest:

```bash
kubectl apply -f rbac.yaml
```

This creates a `ClusterRole` named `fluxcd-hass-reader` with `get`, `list`, and `watch` permissions on:

- `gitrepositories`, `helmrepositories`, `helmcharts`, `buckets`, `ocirepositories`, `artifactgenerators`, `externalartifacts` (`source.toolkit.fluxcd.io`)
- `kustomizations` (`kustomize.toolkit.fluxcd.io`)
- `helmreleases` (`helm.toolkit.fluxcd.io`)
- `fluxinstances`, `resourcesets`, `resourcesetinputproviders` (`fluxcd.controlplane.io`)

Edit the `ClusterRoleBinding` subject at the bottom of `rbac.yaml` to match the service account Home Assistant authenticates as (the default is `home-assistant` in the `default` namespace).

> **Controller monitoring** (source-controller, kustomize-controller, etc.) additionally
> requires `get` and `list` on `deployments` in the `apps` API group. Without it the
> integration still starts, but no controller entities appear. Add this rule to the
> ClusterRole in `rbac.yaml` to enable it:
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

### Step 4 — Add the integration in Home Assistant

1. Go to **Settings → Devices & Services**
2. Click **+ ADD INTEGRATION**
3. Search for **FluxCD**
4. Fill in the form:

| Field | Description | Default |
|---|---|---|
| **Access Mode** | `In-Cluster` when Home Assistant runs inside Kubernetes, otherwise `Kubeconfig File` | Kubeconfig File |
| **Kubeconfig Path** | Path to the kubeconfig file — see [Step 2](#step-2--choose-how-home-assistant-reaches-your-cluster). Leave empty to auto-detect | _(empty)_ |
| **Namespace** | Namespace to monitor; leave empty for all namespaces | _(all namespaces)_ |
| **Scan Interval** | Poll frequency in seconds (minimum 10, maximum 3600) | 60 |
| **Label Selector** | Optional Kubernetes label selector, e.g. `app=myapp` | _(none)_ |

You can add the integration more than once — for example one entry per namespace or per label selector.

### Troubleshooting

| Message or symptom | What to do |
|---|---|
| *No kubeconfig file was found* | The path does not exist, or nothing was found in the default locations. Copy the file to `/config/kubeconfig`, or enter its full path. A `~` path is fine, but the file must actually exist there. |
| *Failed to connect to the Kubernetes cluster* | The kubeconfig was found but the cluster could not be reached. Check the API server URL, the certificate, and that the credentials have not expired. |
| No controller entities | Add the `apps`/`deployments` RBAC rule from [Step 3](#step-3--apply-the-kubernetes-rbac). |
| A resource type is missing | That CRD is not installed in the cluster; it is skipped silently (visible at debug level). |

Enable debug logging to see which kubeconfig file was chosen and which resources were fetched:

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.fluxcd_k8s: debug
```

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

## Companion Lovelace Card

The [**fluxcd-topology-card**](https://github.com/dawg-io/fluxcd-topology-card) is an optional companion custom card for Home Assistant dashboards. It visualizes the relationships between FluxCD resources (GitRepositories, HelmRepositories, HelmCharts, HelmReleases, Kustomizations, and more) as an interactive topology graph directly in your Lovelace UI.

It is built to work alongside this integration and enhances the monitoring experience by providing a graphical overview of your FluxCD resource dependencies — but it is entirely optional and not required for this integration to function.

Repository: [fluxcd-topology-card on GitHub](https://github.com/dawg-io/fluxcd-topology-card)

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

## Project Structure

```
custom_components/fluxcd_k8s/
├── __init__.py        # Integration setup and teardown
├── manifest.json      # Integration metadata and requirements
├── const.py           # Constants, CRD definitions, and category groupings
├── config_flow.py     # Configuration UI flow
├── coordinator.py     # DataUpdateCoordinator for polling
├── api.py             # Kubernetes API client with grouped/per-type fetch functions
├── kubeconfig.py      # Kubeconfig path expansion and default-location discovery
├── models.py          # Data models and kind-specific parsing helpers
├── sensor.py          # Sensor entity platform
├── strings.json       # UI strings
└── translations/
    └── en.json        # English translations
```

## License

This project is provided as-is for monitoring FluxCD resources in Home Assistant.
