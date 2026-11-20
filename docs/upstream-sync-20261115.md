# 2026-11-15 每周上游同步：验证阻塞，未发布

## 基线和范围

- origin：`https://github.com/quark-mac/AzurLaneAutoScript`，目标 `master`。
- upstream：`https://github.com/guoh064/AzurLaneAutoScript.git`，分支 `main`。
- 已 fetch 两个远程；干净工作分支与 `origin/master` 一致，无分叉。
- 基线：`d757bd2e6ebba137961ab0319eeec8f29e349065`。
- 待合入上游：`c710cf29475a8ac98fc21e7763647c6be4f1feb6`，9 个新提交。
- 分支：`openchamber/nimble-circuit`；操作仅在本次独立 worktree。
- 使用 `D:/AzurLaneAutoScript/toolkit/python.exe`（3.7.6），每次先将 worktree 插入 `sys.path[0]`，并断言 `module.config.config_updater.__file__` 位于该 worktree。

## 合并及冲突

执行普通 `git merge --no-ff --no-commit upstream/main`，仅 `module/config/i18n/zh-TW.json` 冲突。

查阅 `79e2a049f` 和上游 `7526e7e1a` 的变更后确认：本地上次配置生成调整了历史开发季键顺序，上游则修正台服开发季名称及说明。逐字段采用上游季名修正，保留本地键顺序及所有定制翻译，再运行配置生成器。没有整文件选择 ours/theirs。

自动合并的岛屿配方实现与上游仅保留原有空白清理差异。其余上游更新涉及订单选中确认、长列表底部确认、派遣失败返回、空闲渔场兑换及作战档案菜单退出。

## 定制行为逐项核验

以下依据健康检查、与基线的源码差异核对及日志清理测试；不代表无人值守游戏实测。

| 清单项 | 核验结果 |
|---|---|
| 1 独立 AutoStart 开关与延迟 | 源码/配置未变，健康检查通过 |
| 2 等待 WebUI 初始化及避免重复启动 | `gui.py` 未变，初始化接线检查通过 |
| 3 Scheduler.Enable 可见 | CSS 未变，检查通过 |
| 4 委托/科研/收获开关解锁 | override 和生成控件检查通过 |
| 5 配置加载不强制重开任务 | 配置实现未变，检查通过 |
| 6 八类日常任务默认关闭 | 源配置未变，生成配置及模板检查通过 |
| 7 解锁后设备 serial 不被破坏 | 连接实现未变，检查通过 |
| 8 委托舰船不足开关与超时 | 委托实现未变，配置/接线检查通过 |
| 9 状态展示及调度启动清除 | 状态链路相关文件未变，检查通过 |
| 10 按保留天数清理日志 | 边界及无日期文件保留测试通过 |
| 11 清理过期错误快照 | 毫秒目录时间戳边界测试通过 |
| 12 清理旧截图及空子目录 | 截图保留边界、空/非空子目录测试通过 |
| 13 启动/每日清理独立开关 | 源码未变，接线、线程去重及停止信号检查通过 |
| 14 原字符串先验证后转换 | WebUI 未变，调用顺序及正则边界检查通过 |
| 15 多语言反馈及按需生成 | 生成器未变，四语言反馈检查通过 |
| 16 空输入不即时回填 | WebUI 未变，检查通过 |
| 17 启动更新失败恢复及手动更新 | 两套 GitManager 和 WebUI Updater 未变，检查通过 |
| 18 空 Git 历史多条查询返回列表 | Updater 未变，检查通过 |

继承的 GemsFarming、装备码、Island 任务/规划器、资源仪表盘入口及原有实现保留；岛屿相关变动按上游合并。侵蚀 1 调度衔接、EventShopScroll、旧餐厅服务员配置迁移、20260625 T1/HT1 bottom 定位的源码未变且健康检查通过。没有以替代实现删除清单行为。

## 验证结果

- 合并前、合并后 `scripts/check_custom_features.py` 均通过。
- `ConfigGenerator().generate()` 成功；再次生成前后逐受控文件 SHA-256 比较无变化。
- `compileall`：`gui.py alas.py module campaign deploy scripts` 全部通过。
- `git diff --check` 和 `git diff --cached --check` 通过。
- `dev_tools/test_log_cleaner.py`：20 通过、0 失败，测试目录已由脚本清理。
- 5 个直接变更测试文件：158 通过、11 缺截图失败。
- 完整 `tests/`：1,869 通过、105 失败；失败分为 104 项 `ScreenshotNotFound` 和 1 项 Windows `cn`/`CN` 断言。
- 104 项缺截图中，101 项对应已记录限制，另 3 项是本次上游新增测试，**不得作为既有豁免**。
- 测试依赖安装在临时独立目录；初次导入遇旧 typing_extensions 优先级问题，调整为 worktree 优先、临时依赖其次，并使用兼容 uiautomator2 的 packaging 20.9 后完成测试。显式加载 `module.testing.screenshot` 插件后核实缺失素材异常。未修改运行 toolkit。

测试调用使用 `pytest.main(['-q', '-p', 'no:cacheprovider', '-p', 'module.testing.screenshot', '--tb=short', 'tests'])`，禁用外部插件自动加载。JUnit 结果保存于 `C:/Users/Administrator/AppData/Local/Temp/opencode/alas-sync-20261115-tests.xml`。

## 发布阻塞与恢复条件

`tests/island/test_order.py::TestSelectedOrderJP` 新增的三项测试缺少：

- `collection/island/order/adjacent_regular_orders_jp.png`
- `collection/island/order/selected_season_order_jp.png`
- `collection/island/order/cooldown_with_speedup_button_jp.webp`

上游和 origin 的 Git 树均没有 `collection/` 素材。取得原始截图后可补跑识别测试。

11 月 15 日首次运行未提交或推送，保留合并供继续处理。11 月 20 日经用户确认，缺少素材的截图测试作为未验证项记录，不再阻止发布；相关 5 项订单逻辑测试通过。未修改测试、断言或识别逻辑。

## 远程与本机部署状态

- 停止前再次 fetch origin，并通过 `git ls-remote origin refs/heads/master` 确认 GitHub 仍为 `d757bd2e6ebba137961ab0319eeec8f29e349065`。
- 本地主 `master` 引用仍为 `2d99b6d9ba42240d23e0707fcf14db241b3d9dae`；这只是源码引用，不是对运行进程已加载版本的确认。
- 未在实际运行目录执行更新、源码写入或部署，未重启进程、未操作游戏、未改变 03:50 更新时刻。
- 每周日 09:00 Asia/Shanghai 的既有任务仍启用，独立 worktree、`baseBranch=origin/master`、`cleanupWorktree=false`；GitHub Actions 仍仅手动触发。
