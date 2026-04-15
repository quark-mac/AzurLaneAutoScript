# 上游同步指南

本文档说明如何自动和手动同步上游仓库 `guoh064/AzurLaneAutoScript`。

## 自动同步（GitHub Actions）

### 工作原理

- **触发时间**：每天 UTC 00:00（北京时间 08:00）自动运行
- **同步策略**：使用 `git merge` 合并上游更新
- **成功时**：自动推送到你的 fork
- **失败时**：创建 GitHub Issue 通知你需要手动处理冲突

### 手动触发

1. 访问：`https://github.com/quark-mac/AzurLaneAutoScript/actions`
2. 选择 "Sync Upstream" workflow
3. 点击 "Run workflow" 按钮
4. 选择 `master` 分支
5. 点击 "Run workflow" 确认

### 查看运行状态

访问：`https://github.com/quark-mac/AzurLaneAutoScript/actions/workflows/sync-upstream.yml`

---

## 手动同步

### 方法 1：使用 Git 别名（推荐）

已配置两个便捷别名：

#### 日常同步（使用 merge）
```bash
git sync
```

等同于：
```bash
git fetch upstream
git merge upstream/main
git push origin master
```

**使用场景**：日常同步，每周或每月执行

#### 定期清理（使用 rebase）
```bash
git sync-clean
```

等同于：
```bash
git fetch upstream
git rebase upstream/main
git push origin master --force-with-lease
```

**使用场景**：每季度执行一次，保持提交历史清晰

---

### 方法 2：完整命令

如果别名不可用，可以使用完整命令：

#### 使用 Merge（推荐）
```bash
# 1. 获取上游更新
git fetch upstream

# 2. 合并上游
git merge upstream/main

# 3. 如果有冲突，解决后：
git add <冲突文件>
git commit

# 4. 推送
git push origin master
```

#### 使用 Rebase（历史更清晰）
```bash
# 1. 获取上游更新
git fetch upstream

# 2. Rebase
git rebase upstream/main

# 3. 如果有冲突，解决后：
git add <冲突文件>
git rebase --continue

# 4. 推送（需要强制推送）
git push origin master --force-with-lease
```

---

## 冲突处理

### 常见冲突文件

1. **配置文件**
   - `config/template.json`
   - `module/config/argument/args.json`
   - `module/config/argument/argument.yaml`

2. **翻译文件**
   - `module/config/i18n/zh-CN.json`
   - `module/config/i18n/en-US.json`
   - `module/config/i18n/ja-JP.json`
   - `module/config/i18n/zh-TW.json`

3. **核心文件**
   - `alas.py`
   - `module/webui/app.py`
   - `module/config/config_updater.py`

### 冲突解决策略

#### 策略 1：保留你的修改
```bash
git checkout --ours <文件>
git add <文件>
```

#### 策略 2：保留上游修改
```bash
git checkout --theirs <文件>
git add <文件>
```

#### 策略 3：手动合并
```bash
# 编辑文件，解决冲突标记：
# <<<<<<< HEAD
# 你的修改
# =======
# 上游的修改
# >>>>>>> upstream/main

# 保存后：
git add <文件>
```

### 冲突解决后

**如果使用 merge**：
```bash
git commit
git push origin master
```

**如果使用 rebase**：
```bash
git rebase --continue
# 如果还有冲突，重复解决过程
# 全部解决后：
git push origin master --force-with-lease
```

---

## 添加新功能的建议

### 方式 1：直接在 master 开发（简单）

```bash
# 1. 确保是最新的
git sync

# 2. 开发新功能
# 编辑文件...

# 3. 提交
git add .
git commit -m "feat: Add new feature"
git push origin master
```

### 方式 2：使用功能分支（推荐）

```bash
# 1. 创建功能分支
git checkout -b feature/new-feature

# 2. 开发新功能
# 编辑文件...

# 3. 提交到功能分支
git add .
git commit -m "feat: Add new feature"
git push origin feature/new-feature

# 4. 合并到 master
git checkout master
git merge feature/new-feature
git push origin master

# 5. 删除功能分支（可选）
git branch -d feature/new-feature
git push origin --delete feature/new-feature
```

---

## 推荐工作流程

### 日常工作流

```
每周/每月：
  1. 自动同步（GitHub Actions）
     或手动执行：git sync
     ↓
  2. 如果有冲突，手动解决
     ↓
  3. 开发新功能
     ↓
  4. 提交并推送

每季度（可选）：
  1. 清理提交历史
     git sync-clean
     ↓
  2. 解决冲突（如果有）
     ↓
  3. 验证功能正常
```

---

## 故障排除

### 问题 1：GitHub Actions 失败

**症状**：收到 Issue 通知，提示同步失败

**解决**：
1. 查看 Actions 运行日志
2. 本地手动同步：`git sync`
3. 解决冲突后推送
4. 关闭 Issue

### 问题 2：推送被拒绝

**症状**：`git push` 提示 `rejected`

**原因**：远程有新的提交

**解决**：
```bash
git pull origin master
# 解决冲突（如果有）
git push origin master
```

### 问题 3：Rebase 冲突太多

**症状**：`git rebase` 遇到大量冲突

**解决**：
```bash
# 中止 rebase
git rebase --abort

# 改用 merge
git merge upstream/main
# 解决冲突
git push origin master
```

### 问题 4：不小心强制推送覆盖了提交

**症状**：提交丢失

**解决**：
```bash
# 查看 reflog
git reflog

# 找到丢失的提交 ID
# 恢复到该提交
git reset --hard <提交ID>

# 重新推送
git push origin master --force-with-lease
```

---

## 配置文件位置

- **GitHub Actions Workflow**：`.github/workflows/sync-upstream.yml`
- **Git 别名配置**：`.git/config`（本地）

---

## 相关链接

- **上游仓库**：https://github.com/guoh064/AzurLaneAutoScript
- **你的 Fork**：https://github.com/quark-mac/AzurLaneAutoScript
- **Actions 页面**：https://github.com/quark-mac/AzurLaneAutoScript/actions
- **Issues 页面**：https://github.com/quark-mac/AzurLaneAutoScript/issues

---

## 总结

- ✅ **自动同步**：GitHub Actions 每天自动运行
- ✅ **手动同步**：使用 `git sync` 命令
- ✅ **定期清理**：使用 `git sync-clean` 命令
- ✅ **冲突处理**：收到通知后手动解决
- ✅ **功能开发**：直接在 master 或使用功能分支

**推荐频率**：
- 自动同步：每天（已配置）
- 手动检查：每周
- 历史清理：每季度
