# 上游同步指南

本文档说明当前可用的自动同步方案：**以 `upstream/main` 为基准，自动重放 `master` 的最终 overlay diff，成功就自动推送，失败才人工介入**。

---

## 机制概览

同步脚本：`scripts/sync_overlay.ps1`

工作流程：

1. `git fetch origin` 和 `git fetch upstream`
2. 计算 `upstream/main` 与 `origin/master` 的共同祖先 `merge-base`
3. 取 `origin/master` 相对 `merge-base` 的最终差异作为 overlay
4. 在新的 `upstream/main` 上用三方合并方式套用这份 overlay
5. 套用成功后提交一个新的 overlay commit
6. 如果传了 `-Push`，再把结果推回 `origin/master`

核心命令模型：

```bash
git merge-base upstream/main origin/master
git diff --binary <merge-base> origin/master
git checkout -B sync/overlay upstream/main
git apply --3way --index overlay.patch
```

---

## 三方合并

`git apply --3way` 的“三方”是：

1. **BASE**：`merge-base` 时的旧文件
2. **OURS**：当前要应用到的新 `upstream/main`
3. **THEIRS**：从 `origin/master` 提取出来的最终 overlay diff

它不是逐个 replay 历史 commit，而是只重放“当前最终想要的结果”。这能避免把中间无效提交、已撤销提交、旧 cherry-pick 历史一起带进去。

---

## 为什么这样做

以前的 `merge` / `cherry-pick` 方式有两个问题：

1. upstream 只要改了同一个文件，哪怕没改同一个函数，也容易反复冲突
2. 逐个提交重放会把中间过程也当成维护对象，历史越久越碎

现在的 overlay 模式只维护**最终差异**：

- 不保留中间无效提交
- 不把旧的调试提交重复 replay
- 生成文件、i18n、template 等可以直接按最终结果重建

这就是这套系统比 cherry-pick 更稳的地方。

---

## GitHub Actions

工作流文件：`.github/workflows/sync-upstream.yml`

现在的行为是：

- 定时运行
- 如果 `upstream/main` 已经包含在 `origin/master`，直接跳过
- 如果有新 upstream，调用 `scripts/sync_overlay.ps1 -Push`
- 如果 overlay 能成功套用，自动推送到 `master`
- 如果 overlay 套不上，创建 Issue 提醒人工处理

这意味着：**平时自动同步，只有真正需要人工判断时才停下来。**

---

## 本地测试

### Dry run

```bash
./scripts/sync_overlay.ps1 -Force
```

作用：

- 即使当前 `origin/master` 已经包含 `upstream/main`，也强制执行一次 overlay 重放
- 适合验证脚本逻辑和补丁可套用性
- 不推送到远端

### 正式同步

```bash
./scripts/sync_overlay.ps1 -Push
```

作用：

- 自动计算 overlay diff
- 套用到新的 `upstream/main`
- 成功后推送到 `origin/master`

运行前要求：

- 工作区必须干净
- 不能有未提交修改

---

## 常见冲突来源

即使这套 overlay 模式已经比 cherry-pick 稳，以下文件仍然是高风险区：

- `module/config/argument/*.yaml`
- `module/config/i18n/*.json`
- `config/template.json`
- `module/webui/app.py`
- 大型 assets / island 相关模块

原因很简单：这些文件要么是生成链的一部分，要么 upstream 也在频繁改动。

---

## 当前结论

这套机制已经实际跑通过：

- `merge-base` 取对了
- overlay diff 取对了
- `git apply --3way --index` 能正确套用
- dry run 可成功生成 overlay commit

所以现在的维护策略就是：**用 overlay 取代逐提交 cherry-pick。**
