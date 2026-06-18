# 上游同步指南

本文档说明当前安全同步策略：**保留 Git 历史，使用普通 merge 自动同步 upstream。**

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
5. 无冲突时自动推送到 `master`
6. 有冲突时停止并创建 Issue，等待人工处理

核心命令模型：

```bash
git fetch upstream
git checkout -B master origin/master
git merge --no-ff upstream/main -m "Merge upstream main"
git push origin master
```

---

## 手动同步

```bash
git fetch upstream
git merge upstream/main
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
- 大型 assets / island 模块

原因：上游更新频繁，本地又维护配置系统、WebUI 和同步相关改动。只要双方改同一文件，Git 就可能要求人工确认。

---

## 当前结论

- 平时：GitHub Actions 自动 merge upstream 并推送
- 冲突时：创建 Issue，人工处理一次
- 不再使用 overlay force push
- 不再自动改写 `master` 历史

这会牺牲一部分“完全自动化”，但能避免 ALAS 更新逻辑因为历史被重写而失败。
