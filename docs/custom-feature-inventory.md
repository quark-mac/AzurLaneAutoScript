# 定制功能历史核验清单

核验日期：2026-11-13。来源：GitHub `quark-mac/AzurLaneAutoScript` 提交 API、完整本地 Git 历史（包括历史备份分支）、原始提交 diff，以及恢复的同步提交 `79e2a049f`。

## 结论与口径

用户记忆中的“十几项”包含功能、修复及同一模块的不同能力，不能仅用 AutoStart、LogCleaner 等模块数量概括。下列 **18 项运行功能/行为均在本次待发布树中保留**。源码、配置和入口保留不等于所有游戏场景都经过实机验收。

| # | 功能/行为 | 历史证据 | 当前实现/核验点 |
|---|---|---|---|
| 1 | 每个配置独立启用自动启动和延迟 | `9509b3793` | `gui.py:auto_start_scheduler`、AutoStart YAML/模板/四语言 |
| 2 | 等待 WebUI 初始化后启动，避免重复启动 | `766e5e8bd` | `while not State._init`、`if not manager.alive` |
| 3 | 显示 Scheduler.Enable 复选框 | `cef7ab253` | `assets/gui/css/alas.css` 不再隐藏控件 |
| 4 | 委托/科研/收获开关解锁 | `b18d893ce` | override.yaml 无 lock，args.json 为 checkbox |
| 5 | 用户关闭任务后加载配置不强制重开 | `b18d893ce` | `AzurLaneConfig.override` 移除 force-enable |
| 6 | 新配置八类日常任务默认关闭 | `b18d893ce` | 委托、战术学院、科研、后宅、指挥喵、大舰队、收获、白嫖；default.yaml、args.json、template.json 一致 |
| 7 | 解锁开关后设备连接仍可用，移除条件性破坏 serial 的逻辑 | `b18d893ce` | `module/device/connection_attr.py` 保留代理清理，不再根据 lock 控件数量修改序列号 |
| 8 | 委托舰船不足检测，可配置开关和超时 | `a02500e0f`、`b614e652c` | `module/commission/commission.py`、Commission 配置 |
| 9 | WebUI 实时显示委托不足状态，调度器重启清除状态 | `a02500e0f`、`8e93ead11` | 状态文件 → ProcessManager → `(state, msg)` → 翻译，`alas.py` 启动清除 |
| 10 | 按保留天数清理文本日志 | `bb319bf9c` | `LogCleaner._clean_log_files`；日期边界保留 |
| 11 | 清理过期错误快照目录 | `bb319bf9c` | `_clean_error_dirs`，毫秒时间戳目录 |
| 12 | 清理配置路径下的旧截图和空子目录 | `bb319bf9c` | `_clean_screenshots`，保留 SaveFolder 根目录 |
| 13 | 启动清理和每日定时清理独立开关 | `bb319bf9c` | `alas.py` 接入；线程去重、停止信号、ScheduledTime |
| 14 | 输入原字符串先验证再转换类型，非法值不保存 | `364c24822` | `_save_config`；延迟 0–600、保留天数 1–365、HH:MM |
| 15 | 多语言错误反馈及优先级，按需生成反馈字段 | `364c24822` | i18n → YAML → 通用提示；四语言 invalid_feedback，生成器仅对 validate 字段生成 |
| 16 | 清空输入框不即时弹回默认值 | `a400ef7df` | 磁盘保存默认值，但不对当前输入控件执行 pin 回填 |
| 17 | Git 更新失败仍能启动；手动更新不受 AutoUpdate=false 限制且错误不被吞掉 | `85ed34789`、`4c382037b` | deploy 两套 GitManager 容错，WebUI Updater 直接执行 git_repository_init 并保留重试 |
| 18 | 无 Git 历史时，多条查询返回空列表 | `4c87e4862` | `Updater.get_commit(n>1)` 返回 `[]`，单条保持四元组 |

## 同步基础设施（另计，不冒充游戏功能）

- `434436ce9`：自动同步能力；本次按用户要求改由 OpenChamber 每周日 09:00（Asia/Shanghai）执行，GitHub Actions 仅保留 workflow_dispatch。
- `30bf94487`：上游无新提交则跳过，保留。
- `d1a9ceb11`：普通 merge、保留历史，替代旧 rebase/cherry-pick/overlay/force-push 试验。
- `1ec58c8d0`、`5194a3e7b`：同步后健康检查，保留并扩充。
- 自动化发布前必须实际运行检查；检查失败不发布，不以削弱清单或删除检查作为解决办法。

## 不是本次遗漏的历史变更

| 历史项 | 证据及判断 |
|---|---|
| 5 秒输入保存防抖 | `b2de07d3d` 曾引入；`06f491a20` 明确从 5 秒改回 1 秒并删除 pin 回填。当前 1 秒是后续修复的预期，不恢复旧 workaround。 |
| 自定义 Docker 镜像工作流 | `41fdcd0bf` 创建；历史分支 `05818b07e` 删除，重写后的 `434436ce9` 提交说明也记录移除。当前不在，不属于本次同步丢失；若需要应作为单独恢复需求。 |
| 舰队菜单 0.1 亮度阈值 | `b18d893ce` 附带修改；上游 `31aa56d2e` 用 FleetBarDetector 取代整套旧算法。本次合并采用新检测器，旧方法无调用方。 |
| 后端 LogCleaner 非法输入自动重置 | `bb319bf9c` 引入，`364c24822` 明确移除，由前端原字符串验证接管。 |
| 多套旧同步方式、overlay 脚本 | 已由 `d1a9ceb11` 普通 merge 策略替代，不恢复历史重写流程。 |

## 其他继承的 fork 能力和合并修复

这些不都由用户原创，但属于应继续保留的现有行为：GemsFarming、装备码、Island 全套任务/规划器、资源仪表盘；`module/os/map.py` 的侵蚀 1 练级调度衔接、`EventShopScroll` 活动商店滚动识别、旧餐厅服务员配置迁移、20260625 T1/HT1 地图 bottom 定位。已检查与上游差异，健康检查覆盖关键入口和仍独立的补丁。

## 验证范围

- `scripts/check_custom_features.py`：源码接入、生成配置、四语言反馈、正则边界、任务默认值、状态和更新行为结构、LogCleaner 与保留的 fork 补丁。
- `dev_tools/test_log_cleaner.py`：20 项真实临时文件清理和保留边界检查。
- 上一轮同步：1,855 项可运行上游测试通过，88 个任务/运行时导入通过，WebUI/自动启动/日志清理已实机观察；101 项截图测试素材缺失、1 项 Windows 大小写断言限制单独记录。
- 本次增加隔离行为验证，直接执行现有 `_save_config`、`get_status_with_message` 和 `get_commit` 方法，外部 IO 使用替身，不接触用户配置或游戏。
- 委托不足等依赖游戏状态的分支目前有源码/接线核验，不宣称全部实机重现。收获一键领取被资源上限拦住是独立运行问题，不在本清单中伪报为已修复。

## 2026-11-13 本地未发布提交回退

reflog 显示 15:19:14 主目录执行了 `reset: moving to origin/master`，将 `79e2a049f` 回退至 `2d99b6d9b`。ALAS 更新器在 KeepLocalChanges=false 时会执行这种 reset；reflog 本身不能确认执行者。已从 Git 对象恢复 `79e2a049f` 到独立维护分支，发布先更新远程，避免未发布同步成果再次被旧远程覆盖。
