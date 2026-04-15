# ALAS 自定义状态系统文档

## 概述

本文档描述 ALAS (AzurLaneAutoScript) 的自定义状态显示系统，用于在主界面左上角显示额外的运行状态信息（如"运行中（委托可用船只不足）"）。

## 系统架构

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                      子进程 (任务执行)                       │
│  ┌──────────────────┐                                       │
│  │ 任务模块          │  1. 检测到状态变化                  │
│  │ (commission.py)   │  2. 写入状态文件                     │
│  │                  │     ./config/.status_{config_name}   │
│  └──────────────────┘                                       │
└──────────────────────────────┬──────────────────────────────┘
                                 │ 文件 IPC
┌──────────────────────────────┼──────────────────────────────┐
│                      主进程 (GUI)                          │
│                              ▼                               │
│  ┌──────────────────────────────────────┐                 │
│  │ Switch 轮询机制 (每 2 秒)              │                 │
│  │                                      │                 │
│  │ get_status_with_message()            │                 │
│  │   └── 返回 (state, status_code)      │                 │
│  │       元组检测状态变化                │                 │
│  │                                      │                 │
│  │ set_status(tuple)                    │                 │
│  │   └── 解析并显示自定义消息            │                 │
│  └──────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 状态码定义

状态码存储在 `i18n` 文件中，支持多语言：

```json
// module/config/i18n/zh-CN.json
"Gui.Status": {
  "Running": "运行中",
  "Inactive": "闲置",
  "Warning": "发生错误",
  "Updating": "等待更新",
  "CommissionShipInsufficient": "委托可用船只不足"
}
```

## 当前实现

### 已集成的状态

| 状态码 | 触发条件 | 显示文本 |
|--------|----------|----------|
| `commission_ship_insufficient` | 委托任务点击推荐按钮后，在配置时间内未出现开始按钮（默认15秒） | 运行中（委托可用船只不足） |

### 相关文件位置

| 文件 | 功能 | 关键代码 |
|------|------|----------|
| `module/commission/commission.py` | 检测船只不足并写入状态文件 | 第 450-455 行 |
| `module/webui/process_manager.py` | 读取状态文件 | `custom_status_message` 属性 |
| `module/webui/app.py` | 复合状态监控和 UI 显示 | `get_status_with_message()`, `set_status()` |
| `alas.py` | Scheduler 启动时清理状态文件 | 第 651-659 行 |
| `module/config/i18n/*.json` | 状态文本翻译 | `Gui.Status.CommissionShipInsufficient` |

### 配置选项

在 ALAS 设置界面中：

- **Commission → EnableShipCheck**: 启用/禁用船只不足检测
- **Commission → ShipCheckTimeout**: 等待开始按钮出现的超时时间（秒）

## 工作原理

### 1. 状态写入（子进程）

当任务检测到特定条件时，写入状态文件：

```python
# module/commission/commission.py
status_file = f"./config/.status_{self.config.config_name}"
with open(status_file, "w", encoding="utf-8") as f:
    f.write("commission_ship_insufficient")
```

### 2. 复合状态监控（主进程）

Switch 使用复合状态元组 `(state, status_code)`，能同时检测状态值和消息内容的变化：

```python
# module/webui/app.py
def get_status_with_message(self):
    process = getattr(self, "alas", None)
    if process is None:
        return -1
    
    state = process.state  # 基础状态 (1=运行中)
    
    if state == 1:
        msg = process.custom_status_message  # 从文件读取
        return (state, msg)  # 返回元组！
    return state
```

### 3. 状态显示更新

当 Switch 检测到元组变化时，调用 `set_status()` 更新 UI：

```python
def set_status(self, state):
    # 解析元组
    if isinstance(state, tuple):
        state, msg_code = state
        if msg_code == "commission_ship_insufficient":
            custom_msg = t("Gui.Status.CommissionShipInsufficient")
    
    if state == 1:
        status_text = t("Gui.Status.Running")
        if custom_msg:
            status_text = f"{status_text}（{custom_msg}）"
        put_loading_text(status_text, color="success")
```

### 4. 状态重置

当 Scheduler 重启时，自动清理状态文件：

```python
# alas.py
def loop(self):
    # ...
    status_file = f"./config/.status_{self.config_name}"
    if os.path.exists(status_file):
        os.remove(status_file)
    # ...
```

## 未来扩展方案

### 方案 1: 保持当前简单模式（推荐）

**特点**：最新状态覆盖，显示当前主要问题

**添加新状态的步骤**：

1. 在任务模块中写入新状态码：
   ```python
   # module/campaign/campaign.py（示例）
   with open(status_file, "w") as f:
       f.write("campaign_ap_insufficient")
   ```

2. 在 `app.py` 的 `set_status()` 中添加解析：
   ```python
   if msg_code == "campaign_ap_insufficient":
       custom_msg = t("Gui.Status.CampaignApInsufficient")
   ```

3. 在 `i18n` 文件中添加翻译：
   ```json
   "CampaignApInsufficient": "作战档案AP不足"
   ```

**适用场景**：ALAS 通常是顺序执行任务，同一时间主要关注一个阻塞点。

---

### 方案 2: 状态堆栈（显示多个状态）

**特点**：允许多个状态同时存在，显示所有活跃问题

**实现方式**：

1. 使用状态目录代替单个文件：
   ```
   ./config/.status_alas/
     ├── commission_ship_insufficient
     ├── waiting_for_ap
     └── daily_limit_reached
   ```

2. 修改 `custom_status_message` 返回列表：
   ```python
   @property
   def custom_status_message(self) -> list:
       status_dir = f"./config/.status_{self.config_name}"
       if os.path.exists(status_dir):
           return [f for f in os.listdir(status_dir)]
       return []
   ```

3. 修改显示逻辑：
   ```python
   if custom_msgs:  # 现在是列表
       msgs = [t(f"Gui.Status.{m}") for m in custom_msgs]
       status_text = f"{status_text}（{', '.join(msgs)}）"
       # 结果："运行中（委托可用船只不足，AP不足）"
   ```

**优点**：显示所有当前问题  
**缺点**：复杂，需管理多个文件，状态可能堆积过多

---

### 方案 3: 优先级状态（最重要优先）

**特点**：只显示最严重/最重要的状态

**实现方式**：

1. 定义状态优先级：
   ```python
   STATUS_PRIORITY = {
       "request_human_takeover": 100,
       "commission_ship_insufficient": 50,
       "waiting_for_ap": 30,
   }
   ```

2. 写入时判断优先级：
   ```python
   def set_status_code(self, new_code):
       current_priority = STATUS_PRIORITY.get(current_code, 0)
       new_priority = STATUS_PRIORITY.get(new_code, 0)
       if new_priority >= current_priority:
           # 只有更高优先级才覆盖
           write_file(new_code)
   ```

**优点**：不会被次要状态淹没  
**缺点**：需要定义优先级，低优先级状态被隐藏

---

### 方案 4: 时间窗口状态（最新优先）

**特点**：显示最近 N 分钟内的所有状态

**实现方式**：

1. 使用 JSON 存储带时间戳的状态：
   ```json
   {
     "commission_ship_insufficient": "2026-04-05T15:30:00",
     "waiting_for_ap": "2026-04-05T15:35:00"
   }
   ```

2. 只显示最近 5 分钟内的状态：
   ```python
   def get_recent_status(self):
       all_status = json.load(...)
       recent = {k: v for k, v in all_status.items() 
                 if time_diff(v) < 300}  # 5分钟
       return list(recent.keys())
   ```

**优点**：自动清理旧状态  
**缺点**：需要 JSON 格式，时间窗口需要调参

---

## 最佳实践

### 状态码命名规范

建议使用以下格式：
```
{module}_{condition}

例如：
- commission_ship_insufficient
- campaign_ap_insufficient
- raid_ticket_depleted
- dorm_coin_empty
- research_material_lack
```

### 清理时机

状态文件应在以下时机自动清理：
1. Scheduler 启动时（已在 `alas.py` 实现）
2. 任务成功完成时（可选）
3. 用户手动停止时（可选）

### 错误处理

所有文件操作都应使用 `try-except` 包裹，避免影响主流程：
```python
try:
    with open(status_file, "w") as f:
        f.write(status_code)
except Exception as e:
    logger.warning(f"Failed to set status: {e}")
```

---

## 技术细节

### Switch 轮询机制

`Switch` 类（`module/webui/utils.py`）负责监控状态变化：

```python
class Switch:
    def _get_state(self):
        _status = self.get_state()  # 获取初始状态
        yield _status
        while True:
            status = self.get_state()
            if _status != status:     # 状态值变化时
                _status = status
                yield _status         # 触发 status 回调
                continue
            yield -1                  # 状态未变化
```

通过返回元组 `(state, message)`，任何一部分的变化都会被检测到。

### 多进程通信

ALAS 使用多进程架构：
- **主进程**：运行 GUI（`gui.py`）
- **子进程**：运行任务（`alas.py`）

状态文件作为简单的 IPC（进程间通信）机制，因为：
- 子进程无法直接访问主进程的内存对象
- 文件系统是最简单的共享存储
- 不需要额外的进程间通信库

---

## 维护记录

| 日期 | 修改内容 | 相关文件 |
|------|----------|----------|
| 2026-04-05 | 实现复合状态监控机制，解决状态不实时更新的问题 | `module/webui/app.py`, `module/webui/process_manager.py` |
| 2026-04-05 | 添加委托船只不足检测和状态显示 | `module/commission/commission.py`, `alas.py` |
| 2026-04-05 | 添加多语言翻译支持 | `module/config/i18n/*.json` |

---

## 参考

- [ALAS 开发文档](https://github.com/LmeSzinc/AzurLaneAutoScript/wiki/Development)
- [Python multiprocessing 文档](https://docs.python.org/3/library/multiprocessing.html)
