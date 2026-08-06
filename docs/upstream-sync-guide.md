# 上游同步指南

本文档说明当前安全同步策略：**保留 Git 历史，使用普通 merge 自动同步 upstream，并在推送前验证本地功能仍然存在。**

---

## 为什么不用 overlay force push

之前尝试过 overlay 模式：把 `upstream/main` 作为基底，再把本地最终 diff 套上去，然后 `--force-with-lease` 推回 `master`。

这套方式代码层面可以工作，但会重写 `master` 历史，把原来的提交压成一个 overlay commit。ALAS 自带更新逻辑依赖本地 Git 历史，历史被重写后，用户本地仓库容易出现分叉，导致更新失败。

因此当前策略改回：**自动 merge upstream，绝不自动重写 master 历史。**

---

## 自动同步

工作流文件：`.github/workflows/sync-upstream.yml`

行为：

1. 每天 UTC 00:00 自动运行
2. 拉取 `upstream/main`
3. 如果 `upstream/main` 已经包含在 `origin/master` 中，直接跳过
4. 如果有新 upstream，执行普通 merge
5. merge 成功后运行同步验证
6. 验证通过才自动推送到 `master`
7. merge 冲突或验证失败时停止并创建 Issue，等待人工处理

核心命令模型：

```bash
git fetch upstream
git checkout -B master origin/master
git merge --no-ff upstream/main -m "Merge upstream main"
python -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
python scripts/check_custom_features.py
git diff --check
git push origin master
```

---

## 同步验证

自动同步在推送前会执行以下检查：

- `python -m compileall -q gui.py alas.py module`
- `python -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"`
- `git diff --check`
- `git diff --exit-code` 检查生成文件没有未提交变化
- `python scripts/check_custom_features.py`

`scripts/check_custom_features.py` 是本 fork 的自定义功能健康检查，覆盖：

- `AutoStart` 配置和生成属性
- `LogCleaner` 配置和生成属性
- 委托舰船不足检测配置
- 委托舰船不足 WebUI 状态翻译
- `GemsFarming`、`Island*`、`IslandProductionPlanner` 任务入口
- 自定义功能关键文件是否仍存在
- LogCleaner 和 AutoStart 的运行时接入
- WebUI 输入验证规则、反馈生成和空字段行为
- Commission、Research、Reward 的 Scheduler 开关未被强制锁定

如果 upstream merge 成功但这些检查失败，workflow 不会推送 `master`，而是创建或更新 `sync-conflict` Issue。

---

## 手动同步

```bash
git fetch upstream
git merge upstream/main
python -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
python scripts/check_custom_features.py
git diff --check
git push origin master
```

如果冲突：

```bash
# 编辑冲突文件
git add <resolved-files>
git commit
git push origin master
```

---

## 冲突来源

这个仓库高冲突区域主要是：

- `module/config/argument/*.yaml`
- `module/config/argument/args.json`
- `module/config/argument/menu.json`
- `module/config/i18n/*.json`
- `config/template.json`
- `module/webui/app.py`
- `alas.py`
- 大型 assets / island 模块

原因：上游更新频繁，本地又维护配置系统、WebUI 和同步相关改动。只要双方改同一文件，Git 就可能要求人工确认。

---

## 当前结论

- 平时：GitHub Actions 自动 merge upstream 并推送
- 推送前：运行生成器、格式检查、编译检查和自定义功能健康检查
- 冲突或验证失败时：创建 Issue，人工处理一次
- 不再使用 overlay force push
- 不再自动改写 `master` 历史

这会牺牲一部分“完全自动化”，但能避免 ALAS 更新逻辑因为历史被重写而失败。

---

## 降低维护成本的规则

- 本地功能优先新增模块，少改上游核心文件
- 配置改动先改 `argument.yaml` / `task.yaml` / `gui.yaml`，再运行 `ConfigGenerator().generate()`
- 新增 WebUI 文案必须补齐四语言 i18n
- 新增任务必须确认 `task.yaml` 和 `alas.py` 入口同时存在
- 不要在自动同步中使用 rebase、force-push 或 overlay 压扁历史
- 重复冲突可以在本地启用 `git rerere` 辅助复用解决结果

推荐本地启用：

```bash
git config rerere.enabled true
```
