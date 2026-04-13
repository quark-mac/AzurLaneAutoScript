# 配置输入验证系统 — 代码修改明细

本文档列出为实现配置输入验证系统而对原始 ALAS 代码所做的全部修改。

---

## 1. `module/webui/app.py`

### 修改 1：错误提示的三级优先级（`set_group` 方法）

**位置**：`set_group` 方法内，原 `# Invalid feedback` 注释处

**修改前**：
```python
# Invalid feedback
output_kwargs["invalid_feedback"] = t("Gui.Text.InvalidFeedBack", value)
```

**修改后**：
```python
# Invalid feedback - Mixed approach: i18n > argument.yaml > default
feedback_key = f"{group_name}.{arg_name}.invalid_feedback"
custom_feedback = t(feedback_key)
if custom_feedback != feedback_key:
    # i18n translation exists, use multilingual version
    output_kwargs["invalid_feedback"] = custom_feedback
else:
    # Try to get from argument.yaml
    yaml_feedback = deep_get(
        self.ALAS_ARGS, f"{task}.{group_name}.{arg_name}.invalid_feedback"
    )
    if yaml_feedback:
        # Use Chinese version from YAML
        output_kwargs["invalid_feedback"] = yaml_feedback
    else:
        # Use default generic message
        output_kwargs["invalid_feedback"] = t(
            "Gui.Text.InvalidFeedBack", value
        )
```

**说明**：为错误提示增加三级查找优先级：i18n 多语言文件 → argument.yaml 中文兜底 → 通用默认提示。

---

### 修改 2：验证时机前移（`_save_config` 方法）

**位置**：`_save_config` 方法内的 `for k, v in modified.copy().items():` 循环

**修改前**：
```python
for k, v in modified.copy().items():
    valuetype = deep_get(self.ALAS_ARGS, k + ".valuetype")
    v = parse_pin_value(v, valuetype)
    validate = deep_get(self.ALAS_ARGS, k + ".validate")
    if not len(str(v)):
        default = deep_get(self.ALAS_ARGS, k + ".value")
        modified[k] = default
        deep_set(config, k, default)
        valid.append(k)
        pin["_".join(k.split("."))] = default

    elif not validate or re_fullmatch(validate, v):
        deep_set(config, k, v)
        modified[k] = v
        valid.append(k)
        for set_key, set_value in config_updater.save_callback(k, v):
            modified[set_key] = set_value
            deep_set(config, set_key, set_value)
            valid.append(set_key)
            pin["_".join(set_key.split("."))] = to_pin_value(set_value)
    else:
        modified.pop(k)
        invalid.append(k)
        logger.warning(f"Invalid value {v} for key {k}, skip saving.")
```

**修改后**：
```python
for k, v in modified.copy().items():
    valuetype = deep_get(self.ALAS_ARGS, k + ".valuetype")
    validate = deep_get(self.ALAS_ARGS, k + ".validate")

    # Validate BEFORE parsing (regex works on strings)
    v_str = str(v)
    if not len(v_str):
        default = deep_get(self.ALAS_ARGS, k + ".value")
        modified[k] = default
        deep_set(config, k, default)
        valid.append(k)
        pin["_".join(k.split("."))] = default
    elif validate and not re_fullmatch(validate, v_str):
        # Validation failed
        modified.pop(k)
        invalid.append(k)
        logger.warning(f"Invalid value {v_str} for key {k}, skip saving.")
    else:
        # Validation passed or no validation rule, parse and save
        v = parse_pin_value(v, valuetype)
        deep_set(config, k, v)
        modified[k] = v
        valid.append(k)
        for set_key, set_value in config_updater.save_callback(k, v):
            modified[set_key] = set_value
            deep_set(config, set_key, set_value)
            valid.append(set_key)
            pin["_".join(set_key.split("."))] = to_pin_value(set_value)
```

**说明**：将验证步骤移到 `parse_pin_value()` 之前，对原始字符串做正则匹配；只有验证通过后才进行类型转换和保存。

---

## 2. `module/config/config_updater.py`

### 修改 1：`generate_i18n` 的 `deep_load` 默认参数恢复原状

**位置**：`generate_i18n` 方法内的 `deep_load` 内部函数定义

**修改前（错误的中间状态，已还原）**：
```python
def deep_load(keys, default=True, words=("name", "help", "invalid_feedback")):
```

**最终状态**：
```python
def deep_load(keys, default=True, words=("name", "help")):
```

**说明**：默认只处理 `name` 和 `help`，不为所有配置项都生成 `invalid_feedback`。

---

### 修改 2：条件性生成 `invalid_feedback`

**位置**：`generate_i18n` 方法中遍历 `self.argument` 的循环

**修改前**：
```python
for path, data in deep_iter(self.argument, depth=2):
    if path[0] not in dashboard_args:
        if path[0] not in visited_group:
            deep_load([path[0], "_info"])
            visited_group.add(path[0])
        deep_load(path)
    if "option" in data:
        deep_load(path, words=data["option"], default=False)
```

**修改后**：
```python
for path, data in deep_iter(self.argument, depth=2):
    if path[0] not in dashboard_args:
        if path[0] not in visited_group:
            deep_load([path[0], "_info"])
            visited_group.add(path[0])
        # Only add invalid_feedback for items with validate rule
        if "validate" in data:
            deep_load(path, words=("name", "help", "invalid_feedback"))
        else:
            deep_load(path, words=("name", "help"))
    if "option" in data:
        deep_load(path, words=data["option"], default=False)
```

**说明**：只有在 `argument.yaml` 中定义了 `validate` 字段的配置项，才会在 i18n 文件中生成并保留 `invalid_feedback` 字段。

---

## 3. `module/config/argument/argument.yaml`

为以下配置项新增 `validate` 字段（正则表达式）：

```yaml
AutoStart:
  Delay:
    value: 10
    validate: '^([0-9]|[1-9][0-9]|[1-5][0-9]{2}|600)$'

LogCleaner:
  ScheduledTime:
    value: '00:00'
    valuetype: str
    validate: '^([01][0-9]|2[0-3]):[0-5][0-9]$'
  KeepDays:
    value: 7
    validate: '^([1-9]|[1-9][0-9]|[12][0-9]{2}|3[0-5][0-9]|36[0-5])$'
```

**说明**：`validate` 字段的值是正则表达式，在保存配置时对用户输入的原始字符串进行 `re.fullmatch()` 验证。

---

## 4. `module/config/i18n/*.json`（4 个语言文件）

为上述配置项在各语言文件中新增 `invalid_feedback` 字段。

### `zh-CN.json`
```json
"AutoStart": {
  "Delay": {
    "invalid_feedback": "请输入 0-600 之间的整数（秒）"
  }
},
"LogCleaner": {
  "ScheduledTime": {
    "invalid_feedback": "请输入正确的时间格式（HH:MM），例如：08:30"
  },
  "KeepDays": {
    "invalid_feedback": "请输入 1-365 之间的整数"
  }
}
```

### `en-US.json`
```json
"AutoStart": {
  "Delay": {
    "invalid_feedback": "Please enter an integer between 0-600 (seconds)"
  }
},
"LogCleaner": {
  "ScheduledTime": {
    "invalid_feedback": "Please enter correct time format (HH:MM), e.g.: 08:30"
  },
  "KeepDays": {
    "invalid_feedback": "Please enter an integer between 1-365"
  }
}
```

### `ja-JP.json`
```json
"AutoStart": {
  "Delay": {
    "invalid_feedback": "0-600の整数を入力してください（秒）"
  }
},
"LogCleaner": {
  "ScheduledTime": {
    "invalid_feedback": "正しい時刻形式（HH:MM）を入力してください。例：08:30"
  },
  "KeepDays": {
    "invalid_feedback": "1-365の整数を入力してください"
  }
}
```

### `zh-TW.json`
```json
"AutoStart": {
  "Delay": {
    "invalid_feedback": "請輸入 0-600 之間的整數（秒）"
  }
},
"LogCleaner": {
  "ScheduledTime": {
    "invalid_feedback": "請輸入正確的時間格式（HH:MM），例如：08:30"
  },
  "KeepDays": {
    "invalid_feedback": "請輸入 1-365 之間的整數"
  }
}
```

---

## 5. `module/log_cleaner.py`

删除了原有的后端输入验证逻辑，改为直接使用配置值。

### 删除的内容

- **常量**：`DEFAULT_SCHEDULED_TIME`、`DEFAULT_KEEP_DAYS`、`MIN_KEEP_DAYS`、`MAX_KEEP_DAYS`
- **函数**：`validate_scheduled_time(value)`、`validate_keep_days(value)`
- **方法**：`_get_validated_keep_days(self)`、`_get_validated_scheduled_time(self)`

### 修改的调用点

`clean_logs` 方法：
```python
# 修改前
keep_days = self._get_validated_keep_days()

# 修改后
keep_days = self.config.LogCleaner_KeepDays
```

`_scheduler_loop` 方法：
```python
# 修改前
scheduled_time = self._get_validated_scheduled_time()

# 修改后
scheduled_time = self.config.LogCleaner_ScheduledTime
```

**说明**：验证职责已完全转移到 WebUI 层（保存前验证），后端无需再做防御性验证和静默重置。

---

## 修改文件汇总

| 文件 | 修改性质 |
|------|---------|
| `module/webui/app.py` | 新增错误提示三级优先级；验证时机前移至类型转换之前 |
| `module/config/config_updater.py` | `generate_i18n` 按需生成 `invalid_feedback` |
| `module/config/argument/argument.yaml` | 为配置项新增 `validate` 规则 |
| `module/config/i18n/zh-CN.json` | 新增 `invalid_feedback` 翻译 |
| `module/config/i18n/en-US.json` | 新增 `invalid_feedback` 翻译 |
| `module/config/i18n/ja-JP.json` | 新增 `invalid_feedback` 翻译 |
| `module/config/i18n/zh-TW.json` | 新增 `invalid_feedback` 翻译 |
| `module/log_cleaner.py` | 删除后端验证函数和方法，直接读取配置值 |

> **注意**：`module/config/argument/args.json` 和 `menu.json` 是自动生成文件，不要手动编辑，每次修改 `argument.yaml` 后需运行生成器更新。
