# 项目状态报告

> 最后更新：2026-05-22

---

## 仓库信息

| 项目 | 值 |
|------|-----|
| 仓库名 | AzurLaneAutoScript (ALAS) |
| Fork 源 | [guoh064/AzurLaneAutoScript](https://github.com/guoh064/AzurLaneAutoScript) (upstream) |
| 本 Fork | [quark-mac/AzurLaneAutoScript](https://github.com/quark-mac/AzurLaneAutoScript) (origin) |
| 参考 Fork | [sui-feng-cb/AzurLaneAutoScript](https://github.com/sui-feng-cb/AzurLaneAutoScript) (reference-fork) |
| 主分支 | `master` |
| Python | 3.7+（使用 `.\toolkit\python.exe`） |

## 备份分支

| 分支名 | 日期 |
|--------|------|
| `backup-master-20260413` | 2026-04-13 |
| `backup-master-20260427` | 2026-04-27 |
| `backup-master-20260522` | 2026-05-22 |
| `backup-before-switch-to-main` | 分支切换前 |

## 已完成的功能

### 1. 自动启动调度器 (`auto-start scheduler`)
- 提交：`9509b3793`
- 启动 ALAS 后自动执行指定配置
- 修复：等待 State.init() 完成后再启动 (`ca468898b`)
- 修复：CSS 规则隐藏了 Scheduler.Enable 复选框 (`cef7ab253`)
- 修复：移除 Commission、Research、Reward 任务的强制启用锁 (`b18d893ce`)

### 2. 自定义状态显示 (`custom status`)
- 提交：`7c6b341db`
- 委托舰船不足时在 WebUI 显示"Running (Commission ships insufficient)"
- 文档：`docs/status_system.md`

### 3. 日志自动清理 (`LogCleaner`)
- 提交：`731b8c6b7`
- 定时清理过期日志文件
- 配置项：`LogCleaner.ScheduledTime`（清理时间）、`LogCleaner.KeepDays`（保留天数）

### 4. 配置输入验证系统 (`input validation`)
- 提交：`33ef2c927`, `b2de07d3d`, `06f491a20`
- WebUI 保存配置前对用户输入做正则验证
- 无效值显示红框和多语言错误提示，阻止保存
- 已为 `AutoStart.Delay`、`LogCleaner.ScheduledTime`、`LogCleaner.KeepDays` 添加验证规则
- 文档：`docs/input-validation-changes.md`、`docs/input-validation-spec.md`、`docs/input-validation-lessons.md`
- 修复：清空输入框后不再弹回默认值，不打断用户输入 (`06f491a20`)

### 5. 上游自动同步 (`upstream sync`)
- 提交：`05818b07e`
- GitHub Actions 定时同步 upstream 新提交
- 工作流：`.github/workflows/main.yml`
- 修复：权限检查、rebase 策略切换 (`5940d6f6b`)
- 修复：自动检测并 cherry-pick 用户提交 (`ebed4a418`)
- 修复：上游无新提交时跳过同步 (`60449fb8b`)
- 文档：`docs/upstream-sync-guide.md`

### 6. Docker 镜像构建 (`docker-image.yml`)
- 提交：`41fdcd0bf`
- GitHub Actions 自动构建 Docker 镜像

## 最近的修复

| 提交 | 说明 |
|------|------|
| `57743117d` | 修复 AutoUpdate=false 时 GUI 静默跳过更新的问题 |
| `e2db22611` | 修复 get_commit 在 n>1 无历史时返回 tuple 而非空列表 |
| `06f491a20` | 修复清空输入框后立即弹回默认值打断用户输入的 UX 问题 |

## 开发者文档

| 文档 | 内容 |
|------|------|
| `docs/input-validation-spec.md` | 配置验证系统的开发规范和使用指南 |
| `docs/input-validation-changes.md` | 所有代码修改的前后对比明细 |
| `docs/input-validation-lessons.md` | 8 个真实开发踩坑经验 |
| `docs/upstream-sync-guide.md` | 上游同步系统的工作流程和冲突处理 |
| `docs/status_system.md` | 自定义状态的实现机制 |
| `docs/project_status.md` | 本文档 — 项目整体状态 |

## 关键文件修改汇总

| 文件 | 修改内容 |
|------|---------|
| `module/webui/app.py` | 配置验证三级优先级；验证时机前移；删除空值 pin pushback；GUI 更新修复 |
| `module/config/config_updater.py` | `generate_i18n` 按需生成 `invalid_feedback` |
| `module/config/argument/argument.yaml` | 新增 3 个 `validate` 规则；自动启动等配置 |
| `module/config/argument/args.json` | 自动生成 — 包含验证规则 |
| `module/config/i18n/*.json` | 4 语言 `invalid_feedback` 翻译 |
| `module/log_cleaner.py` | 删除后端验证，直接读取配置值 |
| `.github/workflows/main.yml` | 上游同步 GitHub Actions 工作流 |
| `.github/pull.yml` | 自动 PR 配置 |

## Git 代理

```
http.proxy = http://127.0.0.1:7890
https.proxy = http://127.0.0.1:7890
```

## 运行方式

```bash
# Windows 推荐方式
.\Alas.exe

# 或使用 toolkit Python
.\toolkit\python.exe gui.py

# CLI 模式
.\toolkit\python.exe alas.py
```

WebUI 默认地址：`http://localhost:22267`
