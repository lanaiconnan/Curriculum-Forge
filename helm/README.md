# Curriculum-Forge Helm Chart

Helm Chart for deploying Curriculum-Forge to Kubernetes.

## Prerequisites

- Kubernetes 1.20+
- Helm 3.0+
- PV provisioner support in the underlying infrastructure (for persistence)
- Ingress Controller (nginx recommended)

## Installing the Chart

### From local directory

```bash
# Install with default values
helm install curriculum-forge ./helm

# Install with custom values
helm install curriculum-forge ./helm -f my-values.yaml

# Install in custom namespace
kubectl create namespace curriculum-forge
helm install curriculum-forge ./helm -n curriculum-forge
```

### From chart repository (if published)

```bash
helm repo add curriculum-forge https://charts.curriculum-forge.example.com
helm install curriculum-forge curriculum-forge/curriculum-forge
```

## Uninstalling the Chart

```bash
# Uninstall
helm uninstall curriculum-forge

# Uninstall from namespace
helm uninstall curriculum-forge -n curriculum-forge
```

## Configuration

The following table lists the configurable parameters and their default values.

### Global Settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.imageRegistry` | Global Docker registry | `""` |
| `global.imagePullSecrets` | Docker registry secrets | `[]` |
| `global.storageClass` | Global storage class | `""` |

### Gateway (Backend)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gateway.replicaCount` | Number of replicas | `2` |
| `gateway.image.repository` | Image repository | `curriculum-forge-gateway` |
| `gateway.image.tag` | Image tag | `latest` |
| `gateway.image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `gateway.service.type` | Service type | `ClusterIP` |
| `gateway.service.port` | Service port | `8765` |
| `gateway.resources.limits.cpu` | CPU limit | `2000m` |
| `gateway.resources.limits.memory` | Memory limit | `2Gi` |
| `gateway.resources.requests.cpu` | CPU request | `500m` |
| `gateway.resources.requests.memory` | Memory request | `512Mi` |

### UI (Frontend)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ui.replicaCount` | Number of replicas | `2` |
| `ui.image.repository` | Image repository | `curriculum-forge-ui` |
| `ui.image.tag` | Image tag | `latest` |
| `ui.image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `ui.service.type` | Service type | `ClusterIP` |
| `ui.service.port` | Service port | `80` |
| `ui.resources.limits.cpu` | CPU limit | `500m` |
| `ui.resources.limits.memory` | Memory limit | `512Mi` |

### Environment Variables

| Parameter | Description | Default |
|-----------|-------------|---------|
| `gateway.env.LOG_LEVEL` | Log level | `INFO` |
| `gateway.env.TOPIC` | Curriculum topic | `rl_curriculum` |
| `gateway.env.MAX_ITERATIONS` | Max iterations | `100` |
| `gateway.env.PASS_THRESHOLD` | Pass threshold | `0.7` |
| `gateway.env.DIFFICULTY` | Difficulty level | `medium` |
| `gateway.env.GOAL` | Learning goal | `Learn to solve RL tasks` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable Ingress | `true` |
| `ingress.className` | Ingress class name | `nginx` |
| `ingress.annotations` | Ingress annotations | See values.yaml |
| `ingress.hosts` | Ingress hosts | `[{host: forge.example.com}]` |
| `ingress.tls` | TLS configuration | `[]` |

### Persistence

| Parameter | Description | Default |
|-----------|-------------|---------|
| `persistence.checkpoints.enabled` | Enable checkpoints PVC | `true` |
| `persistence.checkpoints.size` | Storage size | `10Gi` |
| `persistence.checkpoints.storageClass` | Storage class | `""` |
| `persistence.templates.enabled` | Enable templates PVC | `true` |
| `persistence.templates.size` | Storage size | `1Gi` |
| `persistence.workspace.enabled` | Enable workspace PVC | `true` |
| `persistence.workspace.size` | Storage size | `5Gi` |

### Profiles

Define curriculum profiles in `values.yaml`:

```yaml
profiles:
  rl_curriculum:
    topic: "rl_curriculum"
    max_iterations: 100
    pass_threshold: 0.7
    difficulty: "medium"
    goal: "Learn to solve RL tasks"
```

### Credentials

Set Feishu/WeChat credentials via command line:

```bash
helm install curriculum-forge ./helm \
  --set gateway.feishu.appId=YOUR_APP_ID \
  --set gateway.feishu.appSecret=YOUR_APP_SECRET \
  --set gateway.weixin.appId=YOUR_APP_ID \
  --set gateway.weixin.appSecret=YOUR_APP_SECRET
```

Or create a Secret manually:

```bash
kubectl create secret generic curriculum-forge-credentials \
  --from-literal=feishu-app-id=YOUR_APP_ID \
  --from-literal=feishu-app-secret=YOUR_APP_SECRET \
  -n default
```

## Examples

### Development deployment

```yaml
# dev-values.yaml
gateway:
  replicaCount: 1
  resources:
    limits:
      cpu: 1000m
      memory: 1Gi

ui:
  replicaCount: 1

ingress:
  enabled: false

persistence:
  checkpoints:
    enabled: false
  templates:
    enabled: false
  workspace:
    enabled: false
```

```bash
helm install curriculum-forge ./helm -f dev-values.yaml
```

### Production deployment

```yaml
# prod-values.yaml
gateway:
  replicaCount: 3
  resources:
    limits:
      cpu: 4000m
      memory: 4Gi

ui:
  replicaCount: 2

ingress:
  enabled: true
  hosts:
    - host: forge.production.example.com
      paths:
        - path: /
          pathType: Prefix
          service: ui
        - path: /api
          pathType: Prefix
          service: gateway
  tls:
    - secretName: curriculum-forge-tls
      hosts:
        - forge.production.example.com

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

```bash
helm install curriculum-forge ./helm -f prod-values.yaml -n production
```

## Upgrading

```bash
helm upgrade curriculum-forge ./helm -n curriculum-forge
```

## Troubleshooting

```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=curriculum-forge

# View logs
kubectl logs -l component=gateway -f

# Describe deployment
kubectl describe deployment curriculum-forge-gateway

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp
```

## File Structure

```
helm/
├── Chart.yaml          # Chart metadata
├── values.yaml         # Default values
├── templates/
│   ├── _helpers.tpl    # Template helpers
│   ├── deployment.yaml # Gateway + UI Deployments
│   ├── service.yaml    # Services
│   ├── configmap.yaml  # ConfigMaps + Secrets
│   ├── ingress.yaml    # Ingress
│   ├── pvc.yaml        # PersistentVolumeClaims
│   └── NOTES.txt       # Post-install notes
└── README.md           # This file
```
