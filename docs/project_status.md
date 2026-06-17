# 项目状态报告

> 最后更新：2026-06-17

---

## 当前状态

这个 fork 目前已经形成了一个可持续维护的 overlay 模型：

- `master` 跟随 `upstream/main` 自动更新
- 本地功能通过 overlay diff 自动重放
- 成功时自动推送，失败时才人工介入

换句话说，现在维护重点不是“手工处理每次 upstream 更新”，而是“保持 overlay 能稳定套用”。

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
| 自动同步脚本 | `scripts/sync_overlay.ps1` |
| GitHub Actions | `.github/workflows/sync-upstream.yml` |
| 同步策略 | `merge-base + final diff + git apply --3way` |
| 成功行为 | 自动推送到 `master` |
| 失败行为 | 创建 Issue，人工处理 |

---

## 已验证的能力

- 自动计算 overlay diff
- 在新 upstream 上重放 overlay
- 保留本地输入验证系统
- 保留自动启动、日志清理、自定义状态等本地功能
- 支持本地 `-Force` dry run

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

### 5. Overlay 同步系统
- 关键文件：`scripts/sync_overlay.ps1`
- 文档：`docs/upstream-sync-guide.md`
- 工作流：`.github/workflows/sync-upstream.yml`

---

## 关键文件

| 文件 | 作用 |
|------|------|
| `module/webui/app.py` | WebUI 输入验证、保存逻辑 |
| `module/config/config_updater.py` | 配置生成与 i18n 生成 |
| `module/config/argument/argument.yaml` | 配置源定义 |
| `module/config/i18n/*.json` | 多语言文案 |
| `config/template.json` | 默认配置模板 |
| `scripts/sync_overlay.ps1` | overlay 同步脚本 |
| `.github/workflows/sync-upstream.yml` | 自动同步工作流 |

---

## 维护提示

- 生成文件不要手改，优先改源 YAML / 代码后再生成
- overlay 同步依赖 `merge-base`，不要改成直接 `git diff upstream/main origin/master`
- 如果 overlay 套用失败，说明本地定制和 upstream 已经真的撞上了，需要人工判断
- overlay 逻辑已通过模拟 upstream 新提交的 dry run 验证

---

## 运行入口

```bash
# GUI
./toolkit/python.exe gui.py

# CLI
./toolkit/python.exe alas.py

# Overlay dry run
./scripts/sync_overlay.ps1 -Force

# Overlay 正式同步
./scripts/sync_overlay.ps1 -Push
```
