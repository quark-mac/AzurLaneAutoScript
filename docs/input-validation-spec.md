# 配置输入验证系统 — 开发与使用规范

---

## 系统概述

ALAS 的配置输入验证系统基于已有的 WebUI 验证框架搭建，整体工作流程如下：

```
用户在 WebUI 输入值
       ↓
保存时读取 args.json 中的 validate 字段
       ↓
   有 validate？
   ┌────┴────┐
  是         否
   ↓          ↓
对原始字符串    直接解析并保存
做正则验证
   ↓
验证通过？
   ┌────┴────┐
  是         否
   ↓          ↓
解析类型并    输入框显示红框
保存配置     显示 invalid_feedback
            配置不会被保存
            写入 warning 日志
```

错误提示文本的查找优先级（三级）：

```
i18n 文件中的 invalid_feedback  ← 最高优先级（支持多语言）
        ↓ 未找到
argument.yaml 中的 invalid_feedback  ← 中文兜底
        ↓ 未找到
通用默认提示 "格式错误。示例：{默认值}"
```

---

## 为配置项添加验证的完整步骤

### 第一步：在 `argument.yaml` 中添加 `validate` 字段

文件路径：`module/config/argument/argument.yaml`

```yaml
ConfigGroup:
  ConfigItem:
    value: 10          # 默认值
    validate: '^正则表达式$'
```

**规则**：
- `validate` 的值是正则表达式字符串，系统使用 `re.fullmatch()` 进行匹配
- 验证针对的是用户输入的**原始字符串**，不是类型转换后的值
- 不要在 `argument.yaml` 里加 `invalid_feedback`——错误提示应放在 i18n 文件中以支持多语言

### 第二步：在各语言的 i18n 文件中添加 `invalid_feedback`

需要修改 4 个文件，路径为 `module/config/i18n/<lang>.json`：

| 文件 | 语言 |
|------|------|
| `zh-CN.json` | 简体中文 |
| `en-US.json` | 英文 |
| `ja-JP.json` | 日文 |
| `zh-TW.json` | 繁体中文 |

在对应的配置项下新增 `invalid_feedback` 字段（与 `name`、`help` 同级）：

```json
"ConfigGroup": {
  "ConfigItem": {
    "name": "配置项显示名称",
    "help": "帮助说明",
    "invalid_feedback": "此处填写该语言的错误提示"
  }
}
```

**注意**：只有在 `argument.yaml` 中有 `validate` 字段的配置项，`invalid_feedback` 才会在重新生成配置时被保留。无 `validate` 的配置项即使手动加了 `invalid_feedback`，下次运行生成器也会被清除。

### 第三步：重新生成配置文件

**每次修改 `argument.yaml` 或 i18n 文件后，必须运行此命令**：

```bash
.\toolkit\python.exe -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
```

该命令会：
- 更新 `module/config/argument/args.json`（WebUI 实际读取的验证规则来源）
- 更新 `module/config/argument/menu.json`
- 重新生成各语言 i18n 文件，**保留**有 `validate` 规则的配置项的 `invalid_feedback`

### 第四步：测试验证

启动 GUI：
```bash
.\toolkit\python.exe gui.py
```

访问 `http://localhost:22267`，进入对应配置页面：

- 输入**有效值**（如 `7`）→ 保存成功，显示"配置已保存"
- 输入**无效值**（如 `500`）→ 输入框出现红框，下方显示错误提示，配置不被保存
- 切换语言后重试 → 错误提示应随界面语言变化

---

## 常用正则表达式参考

| 场景 | 正则表达式 |
|------|-----------|
| 非负整数（无上限） | `^\d+$` |
| 整数范围 0–100 | `^([0-9]\|[1-9][0-9]\|100)$` |
| 整数范围 1–365 | `^([1-9]\|[1-9][0-9]\|[12][0-9]{2}\|3[0-5][0-9]\|36[0-5])$` |
| 整数范围 0–600 | `^([0-9]\|[1-9][0-9]\|[1-5][0-9]{2}\|600)$` |
| 正浮点数 | `^\d+(\.\d+)?$` |
| 时间格式 HH:MM（00:00–23:59） | `^([01][0-9]\|2[0-3]):[0-5][0-9]$` |
| IP 地址 | `^((25[0-5]\|2[0-4][0-9]\|[01]?[0-9][0-9]?)\.){3}(25[0-5]\|2[0-4][0-9]\|[01]?[0-9][0-9]?)$` |
| 端口号 1–65535 | `^([1-9][0-9]{0,3}\|[1-5][0-9]{4}\|6[0-4][0-9]{3}\|65[0-4][0-9]{2}\|655[0-2][0-9]\|6553[0-5])$` |

**验证正则表达式的方法**：
```python
import re
pattern = r'^([1-9]|[1-9][0-9]|[12][0-9]{2}|3[0-5][0-9]|36[0-5])$'
test_values = ['1', '7', '365', '0', '366', 'abc']
for v in test_values:
    print(f'{v}: {bool(re.fullmatch(pattern, v))}')
```

---

## 错误提示文本书写规范

- **说清楚合法范围**，避免只说"格式错误"
- **给出示例**，特别是格式复杂的情况

| 类型 | 推荐写法示例 |
|------|------------|
| 整数范围 | `请输入 1-365 之间的整数` |
| 时间格式 | `请输入正确的时间格式（HH:MM），例如：08:30` |
| 带单位的数值 | `请输入 0-600 之间的整数（秒）` |

---

## 不需要验证的情况

以下类型的配置项**不应该**添加 `validate`，系统本身已有对应控件保证输入合法：

- `type: checkbox`（布尔值，选择框）
- `type: select`（有 `option` 列表的下拉选择）
- `type: datetime`（系统内置 datetime 格式验证）
- `type: textarea`（自由文本，无需限制）

只有 `type: input`（自由文本输入框）中的数值、时间、格式受限字段才需要添加 `validate`。

---

## 关于后端验证

**原则：验证在 WebUI 层做，后端直接信任配置值。**

在为某个功能模块的配置项添加 WebUI 层验证后，如果该模块的后端代码中存在对同一配置项的防御性验证（读取时检查并重置为默认值），应将其删除，以避免：

1. 两套验证逻辑产生不一致
2. 用户看到配置被"静默修改"而不知道原因

LogCleaner 模块已完成此项清理，可参考其修改作为范例。

---

## 故障排查

| 现象 | 排查方向 |
|------|---------|
| 输入无效值但没有红框、能正常保存 | 检查是否运行了 `ConfigGenerator().generate()`；检查 `args.json` 中对应项是否有 `validate` 字段 |
| 输入有效值但无法保存、出现红框 | 检查正则表达式是否正确，用 `re.fullmatch()` 手动测试；注意验证的是字符串而非数字 |
| 错误提示不随语言切换 | 检查对应语言的 i18n 文件中是否有 `invalid_feedback`；检查该配置项在 `argument.yaml` 中是否有 `validate`（无 `validate` 的项 `invalid_feedback` 会被清除） |
| 重新生成配置后 `invalid_feedback` 消失 | 该配置项在 `argument.yaml` 中缺少 `validate` 字段，`ConfigGenerator` 不会为其保留 `invalid_feedback` |
