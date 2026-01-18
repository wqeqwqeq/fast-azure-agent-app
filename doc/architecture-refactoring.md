# 架构重构文档

## 概述

本文档记录了 `generic-ai` 项目的代码组织重构过程，主要涉及：
- Key Vault 客户端的位置和使用模式
- 目录结构优化（infrastructure, core, utils 的职责划分）
- Secret 管理策略
- Lifespan vs Dependency 的使用场景

---

## 目录结构

### 重构前
```
app/
├── db/                      # 数据库层
│   ├── manager.py
│   ├── postgresql.py
│   └── redis.py
├── utils/
│   └── events.py            # SSE 事件流
├── opsagent/
│   └── utils/
│       ├── keyvault.py      # Key Vault 客户端（错误位置）
│       └── settings.py
└── ...
```

### 重构后
```
app/
├── core/                    # 内部基础构建块（无外部依赖）
│   └── events.py            # SSE 事件流工具
│
├── infrastructure/          # 外部服务集成
│   ├── keyvault.py          # Azure Key Vault 客户端
│   ├── manager.py           # 数据库管理器
│   ├── postgresql.py        # PostgreSQL 后端
│   └── redis.py             # Redis 后端
│
├── utils/                   # 纯工具函数（无状态、无副作用）
│   └── (空，留作将来使用)
│
├── opsagent/                # Agent 业务逻辑
│   ├── utils/
│   │   └── settings.py      # Azure OpenAI 配置
│   └── middleware/
│       └── observability.py # Agent 中间件
│
├── routes/                  # API 路由
├── config.py                # 应用配置
├── dependencies.py          # 依赖注入
└── main.py                  # FastAPI 应用入口
```

---

## 目录职责划分

| 目录 | 职责 | 判断标准 | 示例 |
|------|------|----------|------|
| **infrastructure/** | 外部服务集成 | 与外部系统通信（网络调用、SDK） | keyvault.py, postgresql.py, redis.py |
| **core/** | 内部基础构建块 | 无外部依赖，但有状态/副作用 | events.py (ContextVar), config.py |
| **utils/** | 纯工具函数 | 无状态、无副作用 | format_date(), validate_email() |

### 依赖方向
```
routes → opsagent → core ← infrastructure
                 ↘      ↙
                   utils
```

---

## Lifespan vs Dependency

| 特性 | Lifespan | Dependency |
|------|----------|------------|
| **执行时机** | App 启动/关闭时执行**一次** | **每个请求**时执行 |
| **用途** | 初始化共享资源（连接池、客户端） | 获取请求级别数据（用户信息） |
| **生命周期** | 整个应用生命周期 | 单个请求周期 |
| **存储位置** | `app.state` | 函数返回值 |

### 什么该放 Lifespan？
- ✅ 数据库连接池 (PostgreSQL, Redis)
- ✅ Key Vault 客户端（一次初始化）
- ✅ 需要 async startup/shutdown 的资源

### 什么该放 Dependency？
- ✅ 从 `app.state` 获取已初始化的资源
- ✅ 解析请求头（如用户身份）
- ✅ 加载配置（可缓存）

---

## Secret 管理策略

### 设计决策

**方案：启动时预加载所有 secrets，无 TTL**

```python
# app/infrastructure/keyvault.py
class AKV:
    """Azure Key Vault client with pre-loaded secrets.

    All secrets are loaded at startup into memory. No TTL - secrets persist
    for the lifetime of the application.

    Secret rotation should be handled via deployment slot swap:
    1. Deploy new instance to staging slot
    2. Rotate secret in Key Vault
    3. Restart staging slot to fetch new secret
    4. Swap slots for zero-downtime rotation
    """

    def __init__(self, vault_name: str):
        self._secrets: dict[str, str] = {}
        ...

    def load_secrets(self, names: list[str]) -> None:
        """Pre-load all secrets at startup. Fails fast if any secret is missing."""
        for name in names:
            secret = self._client.get_secret(name)
            if secret.value is None:
                raise ValueError(f"Secret '{name}' has no value")
            self._secrets[name] = secret.value

    def get_secret(self, name: str) -> str:
        """Get pre-loaded secret. Raises KeyError if not pre-loaded."""
        return self._secrets[name]
```

### 为什么不用 TTL 缓存？

TTL 缓存会引入**危险窗口期**：
```
时间线：
├─ 0 min: App 启动，fetch secret，缓存 5 分钟 TTL
├─ 2 min: Key Vault secret 被 rotate（旧 secret 立即失效）
├─ 2-5 min: App 用着旧 secret → 💥 不工作
└─ 5 min: TTL 过期，fetch 新 secret → 恢复
```

### Secret Rotation 流程

使用 **Deployment Slot Swap** 实现零停机：
1. Production slot 正在运行（用旧 secret）
2. 在 Staging slot 部署新实例
3. Staging 启动时从 Key Vault fetch（拿到当前 secret）
4. Rotate Key Vault 中的 secret
5. Staging slot 重启（拿到新 secret）
6. Swap slots → Staging 变 Production
7. 零停机完成 ✅

### 需要预加载的 Secrets

| Secret Name | 使用位置 |
|-------------|----------|
| `POSTGRES-ADMIN-PASSWORD` | `app/main.py` - 数据库连接 |
| `REDIS-PASSWORD` | `app/main.py` - Redis 连接 |
| `AZURE-OPENAI-API-KEY` | `app/opsagent/utils/settings.py` - LLM 调用 |
| `APPLICATIONINSIGHTS-CONNECTION-STRING` | 遥测（可选） |

---

## Secret 使用流程

```
┌─────────────────────────────────────────────────────────────────┐
│  Lifespan (启动时)                                               │
├─────────────────────────────────────────────────────────────────┤
│  1. AKV.load_secrets() 预加载所有 secrets 到内存                   │
│                                                                 │
│  2. 用 secrets 初始化各种服务：                                    │
│     ├─ POSTGRES-PASSWORD → 建立数据库连接池                        │
│     ├─ REDIS-PASSWORD → 建立 Redis 连接                           │
│     └─ AZURE-OPENAI-API-KEY → initialize_azure_openai_settings() │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Routes (请求处理时)                                             │
├─────────────────────────────────────────────────────────────────┤
│  Routes 只使用已初始化的资源，不直接访问 secrets：                   │
│                                                                 │
│  • HistoryManagerDep → 从 app.state 获取已建好连接的 manager        │
│  • get_azure_openai_settings() → 获取已初始化的 singleton          │
│                                                                 │
│  Routes 代码完全不需要改！                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 删除的死代码

以下代码被删除，因为在预加载模式下不再需要：

1. **`get_keyvault()` dependency** - Routes 不需要直接访问 Key Vault
2. **`KeyVaultDep` 类型别名** - 同上
3. **`get_appinsights_connection_string()`** - 从 observability.py 删除
4. **Event utilities 的 backward compatibility 导出** - 直接从 `app.core` 导入

---

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `app/infrastructure/__init__.py` | 新建，导出 AKV + 数据库模块 |
| `app/infrastructure/keyvault.py` | 新建，重构后的 AKV 类 |
| `app/infrastructure/manager.py` | 从 db/ 移过来 |
| `app/infrastructure/postgresql.py` | 从 db/ 移过来 |
| `app/infrastructure/redis.py` | 从 db/ 移过来 |
| `app/core/__init__.py` | 新建 |
| `app/core/events.py` | 从 utils/ 移过来 |
| `app/utils/__init__.py` | 清空导出 |
| `app/dependencies.py` | 删除 get_keyvault, 更新导入 |
| `app/main.py` | 重构 lifespan，预加载所有 secrets |
| `app/opsagent/utils/settings.py` | 简化，不再自己访问 Key Vault |
| `app/opsagent/middleware/observability.py` | 只导入 emit_event |
| `app/opsagent/middleware/__init__.py` | 只导出 middleware |
| `app/routes/messages.py` | 更新导入路径 |
| `app/db/` | 删除（已移到 infrastructure/） |
| `app/opsagent/utils/keyvault.py` | 删除 |

---

## 测试

运行 import 测试验证重构正确性：

```bash
uv run python test_import.py
```

预期输出：
```
✓ app.core imports OK
✓ app.infrastructure.keyvault imports OK
✓ app.infrastructure.manager imports OK
✓ app.infrastructure.postgresql imports OK
✓ app.infrastructure.redis imports OK
✓ app.config imports OK
✓ app.dependencies imports OK
✓ app.opsagent.utils imports OK
✓ app.opsagent.middleware imports OK
✓ app.routes imports OK
✓ app.main imports OK

==================================================
SUCCESS: All imports passed!
```

---

## 运行应用

```bash
uv run uvicorn app.main:app --reload
```

**注意**：确保以下 secrets 存在于 Key Vault 中：
- `POSTGRES-ADMIN-PASSWORD`
- `REDIS-PASSWORD`
- `AZURE-OPENAI-API-KEY`
- `APPLICATIONINSIGHTS-CONNECTION-STRING`
