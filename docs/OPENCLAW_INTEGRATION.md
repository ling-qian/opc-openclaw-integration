# OpenClaw 集成文档

## 概述

OPC Platform 通过 `openclaw_service.py` 与 OpenClaw 交互，暴露 REST API 供前端或后端调用。

---

## 架构

```
OPC Platform (FastAPI) 
   └─> /openclaw/* → OpenClawService 
         ├─ EventHistory (JSONL files)
         ├─ EventBus (via Pulse or CLI, future)
         └─ Algorithm (Node.js subprocess)
```

---

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `OPENCLA_WORKSPACE` | `~/.openclaw/workspace` | OpenClaw 工作区根目录 |

---

## API 参考

### 事件发射

```http
POST /openclaw/event/emit
Content-Type: application/json

{
  "type": "user.completed_course",
  "payload": { "user_id": 123, "course_id": 45 },
  "source": "opc-academy"
}
```

响应：
```json
{
  "event_id": "local-1623456789",
  "status": "emitted"
}
```

### 事件查询

```http
POST /openclaw/event/query
{
  "type": "user.completed_course",
  "after": "2026-05-01T00:00:00Z",
  "limit": 50,
  "order": "desc"
}
```

响应：
```json
{
  "events": [ ... ],
  "total": 120,
  "limit": 50,
  "offset": 0,
  "order": "desc"
}
```

### 事件计数

```http
GET /openclaw/event/count?type=user.completed_course&source=opc-academy
```

### 分组统计

```http
GET /openclaw/event/groupBy?field=type&source=opc-academy
```

### 运行算法

```http
POST /openclaw/algorithm/run
{
  "prompt": "设计一个 OpenClaw 企业部署服务套餐",
  "tier": "E3",
  "work_dir": "/tmp/opc-alg-run-123"
}
```

响应（示例）：
```json
{
  "status": "completed",
  "tier": "E3",
  "artifacts": ["thinking", "plan", "build", "execution", "learning"]
}
```

### 集成状态

```http
GET /openclaw/status
```

---

## OPC 中的事件发射点建议

- 用户完成课程 → `user.completed_course`
- 项目投标提交 → `project.bid.submitted`
- 健康打卡完成 → `health.checkin.completed`
- 支付成功 → `payment.succeeded`
- 社区发帖 → `community.post.created`

可以在相应 service 中调用 `openclaw_service.emit_event()`。

---

## 示例调用 (Python)

```python
import requests

BASE = "http://localhost:8000"

# 发射事件
requests.post(f"{BASE}/openclaw/event/emit", json={
  "type": "user.completed_course",
  "payload": {"user_id": 1, "course_id": 2}
})

# 查询
resp = requests.post(f"{BASE}/openclaw/event/query", json={
  "type": "user.completed_course",
  "limit": 10
})
print(resp.json())
```

---

## 生产部署建议

- 设置 `OPENCLA_WORKSPACE` 为持久化路径（如 `/var/lib/openclaw`）
- 确保 OpenClaw 算法技能已部署且 Node.js 可用
- 为 Pulse 配置自动启动，提供实时事件流（未来 SSE 端点）
- 使用 Nginx 代理 `/openclaw` 路径并限制内部访问

---

## 故障排查

| 问题 | 检查点 |
|------|--------|
| 500 错误 | 查看 `openclaw_service.py` 日志；确认 EventHistory 目录可写 |
| Algorithm run 超时 | 确保 `node` 在 PATH 中；检查算法脚本是否安装 |
| 事件不出现 | 当前为本地文件写入，需启动 Pulse 实际路由 |

---

**下一步**：在 OPC 核心业务中插入事件发射，构建完整的事件驱动数据流。
