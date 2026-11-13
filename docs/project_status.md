# 项目状态报告

> 最后更新：2026-11-13

---

## 当前状态

这个 fork 目前采用保留 Git 历史的 upstream merge 模型，并在自动推送前执行本地功能健康检查：

- `master` 跟随 `upstream/main` 自动 merge 更新
- merge 成功后先验证配置生成、Python 编译和自定义功能入口
- OpenChamber 每周日北京时间 09:00 独立 worktree 验证后推送，GitHub Actions 仅手动备用

换句话说，现在维护重点是尽量让普通 merge 自动通过；真正冲突时再手动处理。

---

## 仓库信息

| 项目 | 值 |
|------|-----|
| 仓库名 | `AzurLaneAutoScript` |
| Fork 源 | `guoh064/AzurLaneAutoScript` |
| 本 Fork | `quark-mac/AzurLaneAutoScript` |
| 主分支 | `master` |
| 上游分支 | `upstream/main` |
| Python | 3.7+（推荐 `./toolkit/python.exe`） |

---

## 当前同步机制

| 项目 | 状态 |
|------|------|
| 自动同步 | OpenChamber 每周日 09:00（Asia/Shanghai），独立 worktree |
| GitHub Actions | `.github/workflows/sync-upstream.yml`，仅 workflow_dispatch |
| 同步策略 | 普通 `git merge upstream/main` |
| 成功行为 | 验证通过后自动推送到 `master` |
| 失败行为 | 创建/更新 Issue，人工处理 |
| 健康检查 | `scripts/check_custom_features.py` |

---

## 已验证的能力

完整历史核验见 [定制功能历史清单](custom-feature-inventory.md)：18 项保留的运行功能/行为、同步基础设施、被主动替代或删除的历史方案，以及验证边界。

- 保留本地输入验证系统
- 保留自动启动、日志清理、自定义状态等本地功能
- 保留 Git 历史，兼容 ALAS 自带更新逻辑
- 自动检查关键本地配置、i18n、任务入口和功能文件是否仍存在
- 已同步至 `upstream/main` 提交 `cbf7b8241`（本次合入 216 个上游提交）
- 已恢复同步中被覆盖的 AutoStart、LogCleaner、委托舰船检测和 Scheduler 开关控制

### 2026-11-13 本地验证

- 使用 toolkit Python 3.7.6 完成配置生成、编译和自定义功能健康检查。
- 上游自动化测试：1,855 项通过。101 项截图测试缺少上游未入库的 `collection/` 素材；另 1 项开发工具测试断言目录名为 `CN`，在 Windows 大小写不敏感目录下解析为 `cn`，未计入通过项。相关实现与上游一致，未修改测试。
- `dev_tools/test_log_cleaner.py`：20 项通过，覆盖保留期限边界、日志、错误目录和截图。
- `alas.py` 中 88 个任务及运行时导入通过；现有用户自定义配置经新版本迁移后保持原值。
- 舰队菜单检测冲突采用上游 `FleetBarDetector`，移除已无调用方的旧 `bar_opened` 检测。
- 本地未跟踪的旧岛屿模块及无引用识图资源移至仓库外备份；配置、启动器和仍使用的本地资源保留。
- 同步前恢复分支：`backup/pre-sync-20261113`。
- 本机配置及清理备份：`C:\Users\Administrator\AppData\Local\Temp\opencode\alas-sync-20261113`。

---

## 主要功能模块

### 1. 自动启动调度器
- 启动后自动执行指定配置

### 2. 自定义状态显示
- WebUI 可显示运行状态提示

### 3. 日志自动清理
- 支持定时清理日志

### 4. 配置输入验证系统
- WebUI 保存前验证输入
- 无效输入显示错误提示

### 5. 上游同步系统
- 策略：普通 merge，保留历史
- 文档：`docs/upstream-sync-guide.md`
- 工作流：`.github/workflows/sync-upstream.yml`
- 健康检查：`scripts/check_custom_features.py`

### 6. 同步后保护项
- 验证 AutoStart 和 LogCleaner 配置、翻译及运行时接入
- 验证委托舰船不足检测和状态显示
- 验证 WebUI 正则输入校验和空字段行为
- 验证 Commission、Research、Reward 的 Scheduler 开关未被强制锁定
- 验证 GemsFarming 和 Island 任务入口仍存在
- 验证 IslandTransport 入口、手动更新绕过 AutoUpdate、更新失败仍可启动及空提交历史处理

---

## 关键文件

| 文件 | 作用 |
|------|------|
| `module/webui/app.py` | WebUI 输入验证、保存逻辑 |
| `module/config/config_updater.py` | 配置生成与 i18n 生成 |
| `module/config/argument/argument.yaml` | 配置源定义 |
| `module/config/i18n/*.json` | 多语言文案 |
| `config/template.json` | 默认配置模板 |
| `.github/workflows/sync-upstream.yml` | 自动同步工作流 |
| `scripts/check_custom_features.py` | 自定义功能健康检查 |

---

## 维护提示

- 生成文件不要手改，优先改源 YAML / 代码后再生成
- 不要使用会自动重写 `master` 历史的同步策略，否则 ALAS 自带更新可能失败
- 如果自动 merge 或健康检查失败，说明本地定制和 upstream 已经真的撞上了，需要人工判断

---

## 运行入口

```bash
# GUI
./toolkit/python.exe gui.py

# CLI
./toolkit/python.exe alas.py

# 手动同步 upstream
git fetch upstream
git merge upstream/main
./toolkit/python.exe -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
./toolkit/python.exe scripts/check_custom_features.py
git diff --check
git push origin master
```
