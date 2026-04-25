# Kubernetes Deployment

Curriculum-Forge Kubernetes 部署配置。

## 前置条件

- Kubernetes 集群 (1.20+)
- kubectl 已配置
- Nginx Ingress Controller（可选，用于 Ingress）
- 持久存储类（用于 PVC）

## 快速部署

### 使用 Kustomize（推荐）

```bash
# 预览部署内容
kubectl kustomize k8s/

# 应用所有资源
kubectl apply -k k8s/

# 检查部署状态
kubectl get pods -l app=curriculum-forge
kubectl get services -l app=curriculum-forge
```

### 逐个应用

```bash
# 1. 创建命名空间（可选）
kubectl create namespace curriculum-forge

# 2. 创建持久卷
kubectl apply -f k8s/pvc.yaml

# 3. 创建配置
kubectl apply -f k8s/configmap.yaml

# 4. 部署应用
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 5. 创建 Ingress（可选）
kubectl apply -f k8s/ingress.yaml
```

## 配置说明

### ConfigMap

编辑 `k8s/configmap.yaml` 修改默认配置：

```yaml
data:
  topic: "rl_curriculum"
  max_iterations: "100"
  pass_threshold: "0.7"
  difficulty: "medium"
  goal: "Learn to solve RL tasks"
```

### Secrets（敏感信息）

创建 Secrets 存储敏感信息：

```bash
# 飞书凭证
kubectl create secret generic feishu-credentials \
  --from-literal=app-id=YOUR_APP_ID \
  --from-literal=app-secret=YOUR_APP_SECRET \
  --from-literal=encrypt-key=YOUR_ENCRYPT_KEY \
  --from-literal=verification-token=YOUR_TOKEN

# 微信凭证
kubectl create secret generic weixin-credentials \
  --from-literal=app-id=YOUR_APP_ID \
  --from-literal=app-secret=YOUR_APP_SECRET \
  --from-literal=token=YOUR_TOKEN \
  --from-literal=encoding-aes-key=YOUR_AES_KEY
```

取消注释 `deployment.yaml` 中的 Secret 引用。

### Ingress

修改 `k8s/ingress.yaml` 中的域名：

```yaml
spec:
  tls:
  - hosts:
    - YOUR_DOMAIN.com
```

## 访问服务

### ClusterIP（集群内部）

```bash
# 端口转发
kubectl port-forward svc/curriculum-forge-gateway 8765:8765
kubectl port-forward svc/curriculum-forge-ui 8080:80
```

### NodePort（直接访问）

```bash
# Gateway: http://<node-ip>:30876
# 查看 NodePort
kubectl get svc curriculum-forge-gateway-nodeport
```

### Ingress（生产环境）

```bash
# 配置 DNS 解析后访问
# UI: https://forge.example.com
# API: https://api.forge.example.com
```

## 扩容缩容

```bash
# 扩容到 3 个副本
kubectl scale deployment curriculum-forge-gateway --replicas=3

# 或修改 k8s/deployment.yaml 后重新应用
kubectl apply -k k8s/
```

## 监控和日志

```bash
# 查看 Pod 日志
kubectl logs -f deployment/curriculum-forge-gateway

# 查看所有资源
kubectl get all -l app=curriculum-forge

# 描述部署
kubectl describe deployment curriculum-forge-gateway
```

## 清理

```bash
# 删除所有资源
kubectl delete -k k8s/

# 或逐个删除
kubectl delete -f k8s/ingress.yaml
kubectl delete -f k8s/service.yaml
kubectl delete -f k8s/deployment.yaml
kubectl delete -f k8s/configmap.yaml
kubectl delete -f k8s/pvc.yaml
```

## 生产环境建议

1. **镜像仓库**: 推送镜像到私有仓库
   ```bash
   docker tag curriculum-forge-gateway:latest your-registry/curriculum-forge-gateway:v1.0.0
   docker push your-registry/curriculum-forge-gateway:v1.0.0
   ```

2. **资源限制**: 根据实际负载调整 `resources`

3. **持久存储**: 使用云服务商的 StorageClass

4. **自动扩容**: 配置 HPA
   ```bash
   kubectl autoscale deployment curriculum-forge-gateway --min=2 --max=10 --cpu-percent=70
   ```

5. **监控**: 部署 Prometheus + Grafana（见 P5 计划）

## 文件说明

```
k8s/
├── deployment.yaml     # Gateway + UI 部署
├── service.yaml       # Service 定义
├── configmap.yaml     # 配置和 Profile
├── pvc.yaml           # 持久卷声明
├── ingress.yaml       # Ingress 路由
├── kustomization.yaml # Kustomize 配置
└── README.md          # 本文档
```
