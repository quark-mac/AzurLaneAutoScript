# 配置输入验证系统 — 开发踩坑记录

本文记录在开发配置输入验证系统过程中遇到的真实问题，以及最终的解决思路，供后续开发参考。

---

## 坑 1：ALAS 已有验证框架，但没有人用它

### 背景

最初想为配置项添加输入验证时，第一反应是"这需要从头设计一套系统"。

### 实际情况

ALAS 早就内置了完整的验证框架：

- `module/webui/app.py` 的 `_save_config` 方法中已有读取 `validate` 字段并调用 `re_fullmatch()` 的逻辑
- `module/webui/base.py` 中已有 `pin_set_invalid_mark()` / `pin_remove_invalid_mark()` 方法，负责给输入框加红框
- `module/webui/utils.py` 中的 `re_fullmatch()` 已特殊处理 `datetime` 类型

整个验证流程的基础设施都在，只是 `argument.yaml` 里 344 个配置项没有一个定义了 `validate` 字段。

### 经验

**优先深读现有代码，再决定是否从头建设。** 搜索关键词（`validate`、`invalid`、`pin_set_invalid`）能很快定位到相关逻辑。

---

## 坑 2：验证逻辑在类型转换之后执行，导致所有数值都无法保存

### 问题现象

为 `LogCleaner.KeepDays` 添加验证规则 `^\d+$` 后，输入任何数字（包括合法的 `7`）都无法保存，都会出现红框。

### 根本原因

原始代码的执行顺序是：

```python
v = parse_pin_value(v, valuetype)   # 先把 "7" 转成整数 7
validate = ...
if re_fullmatch(validate, v):        # 再对整数 7 做正则匹配 → 直接报 TypeError
```

`re.fullmatch()` 只接受字符串参数，传入整数会抛出异常，实际效果等同于验证失败。

### 解决方案

把验证步骤移到 `parse_pin_value()` 之前，对原始字符串做匹配：

```python
v_str = str(v)                              # 保持字符串形式
if validate and not re_fullmatch(validate, v_str):
    # 验证失败
    ...
else:
    v = parse_pin_value(v, valuetype)       # 验证通过后再做类型转换
    ...
```

### 经验

**正则表达式只能验证字符串。** 任何涉及正则的验证都应该在类型转换之前进行。遇到"所有值（包括合法值）都无法保存"的现象时，优先检查验证是否在类型转换之前。

---

## 坑 3：修改 argument.yaml 后忘记运行配置生成器，验证规则不生效

### 问题现象

在 `argument.yaml` 里加了 `validate` 字段，启动 GUI 后验证仍然不生效。

### 根本原因

WebUI 实际读取的不是 `argument.yaml`，而是由它生成的 `module/config/argument/args.json`。不运行生成器，`args.json` 不会更新，新加的 `validate` 字段在 WebUI 中永远不可见。

这是 ALAS 配置系统的基本架构：

```
argument.yaml  →（生成器）→  args.json  →（WebUI 读取）→  验证逻辑
```

### 解决方案

每次修改 `argument.yaml` 后必须运行：

```bash
.\toolkit\python.exe -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
```

### 经验

**ALAS 中所有以 `.json` 结尾的配置描述文件都是自动生成的，不要直接编辑。** `AGENTS.md` 的"Common Configuration Pitfalls"节有明确提示，开发前应通读该文档。

---

## 坑 4：切换语言后错误提示仍为中文，i18n 不生效

### 问题现象

直接在 `argument.yaml` 的配置项里加了 `invalid_feedback: '请输入...'`，切换到英文界面后错误提示仍然是中文。

### 根本原因

在 `argument.yaml` 里写死的字符串不经过 i18n 系统，无论界面切换到哪种语言，都会直接显示该字符串的原始内容。

### 解决方案

错误提示应写在各语言的 i18n 文件（`module/config/i18n/*.json`）中，而不是 `argument.yaml`。WebUI 通过 `t("GroupName.ArgName.invalid_feedback")` 调用翻译函数动态查找对应语言的文本。

最终采用三级优先级方案：

1. i18n 文件中的多语言翻译（最优，支持语言切换）
2. `argument.yaml` 中的 `invalid_feedback`（兜底，仅适合快速添加中文）
3. 默认通用提示

### 经验

**任何面向用户展示的文本都要走 i18n 系统，不要直接硬编码字符串。** `argument.yaml` 里的字段不会经过翻译函数，只适合存放机器读取的规则（如正则表达式），不适合存放显示文本。

---

## 坑 5：ConfigGenerator 重新生成时覆盖了 i18n 中手动添加的 invalid_feedback

### 问题现象

在 i18n 文件中手动添加了 `invalid_feedback`，运行一次 `ConfigGenerator().generate()` 后，所有手动添加的 `invalid_feedback` 字段全部消失。

### 根本原因

`generate_i18n` 方法内的 `deep_load()` 函数只保留 `name` 和 `help` 字段，不会读取旧文件中已有的 `invalid_feedback`，重新生成时自然就被清空了。

```python
# 原始代码只保留这两个字段
def deep_load(keys, default=True, words=("name", "help")):
    ...
```

### 解决方案

修改 `generate_i18n` 的逻辑：对有 `validate` 规则的配置项，额外读取并保留 `invalid_feedback`：

```python
if "validate" in data:
    deep_load(path, words=("name", "help", "invalid_feedback"))
else:
    deep_load(path, words=("name", "help"))
```

这样，只要配置项有 `validate` 字段，`invalid_feedback` 在重新生成配置后就会被保留。

### 经验

**理解 ConfigGenerator 的工作机制至关重要。** 它是单向的覆盖式生成，以 YAML 源文件为权威，i18n 文件中任何不在生成逻辑覆盖范围内的字段都会丢失。在修改 i18n 文件内容之前，应先确认 `ConfigGenerator` 是否会保留它。

---

## 坑 6：invalid_feedback 被生成到了所有配置项，污染 i18n 文件

### 问题现象

在修改 `generate_i18n` 使其保留 `invalid_feedback` 时，最初把 `invalid_feedback` 加进了默认的 `words` 元组：

```python
def deep_load(keys, default=True, words=("name", "help", "invalid_feedback")):
```

重新生成后，每一个配置项（共 344 个）都被加上了 `invalid_feedback`，值为其键名字符串（如 `LogCleaner.Enable.invalid_feedback`），i18n 文件体积暴增。

### 根本原因

`deep_load` 对找不到旧值的字段会使用键名作为默认值（`d = ".".join(k) if default else str(word)`），将 `invalid_feedback` 加入默认 `words` 后，所有配置项都会得到这个"占位"字符串。

### 解决方案

不修改默认 `words`，而是在调用处按条件决定是否传入 `invalid_feedback`：

```python
if "validate" in data:
    deep_load(path, words=("name", "help", "invalid_feedback"))
else:
    deep_load(path, words=("name", "help"))
```

这样只有真正有验证规则的配置项才会在 i18n 文件中生成 `invalid_feedback` 槽位。

### 经验

**修改生成器逻辑前，先理解 `deep_load` 的"默认值填充"机制。** 凡是加入 `words` 的字段，在旧文件中不存在时会被填入键名字符串作为占位符——这个占位符会进入生成后的 i18n 文件，如果不加以区分会被当成正常翻译处理。

---

## 坑 7：后端已有验证与 WebUI 验证产生逻辑冲突

### 问题现象

`LogCleaner` 模块在运行时会读取配置值，如果不合法则自动重置为默认值并写回配置。在 WebUI 层添加验证后，出现了两套逻辑并存的情况：用户在 WebUI 输入了合法值并保存成功，但运行时后端按照自己的验证标准将其重置，用户看到配置被"神秘修改"。

### 根本原因

`module/log_cleaner.py` 中的 `validate_scheduled_time()` 和 `validate_keep_days()` 是为了防止配置文件中存在非法值（例如手动编辑 JSON 写错了）而设计的防御性验证。当 WebUI 层已经保证了输入合法，后端验证就变成了多余的，两套标准甚至可能不一致。

### 解决方案

删除后端的验证函数和方法，`LogCleaner` 直接读取并信任配置值：

```python
# 删除 validate_scheduled_time、validate_keep_days、
# _get_validated_scheduled_time、_get_validated_keep_days

# clean_logs 中直接使用：
keep_days = self.config.LogCleaner_KeepDays

# _scheduler_loop 中直接使用：
scheduled_time = self.config.LogCleaner_ScheduledTime
```

### 经验

**引入 WebUI 层验证后，应检查并清理对应模块的后端防御性验证。** 两套验证长期并存会导致：行为不可预期、调试困难、用户困惑。验证职责应该明确：WebUI 层负责拦截用户输入，后端代码信任已保存的配置值。
