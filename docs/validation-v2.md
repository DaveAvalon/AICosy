# V2 验证记录

> 历史开发记录：文中本机 evidence 档案未随公开仓库发布；公开兼容性样本见 `tests/fixtures/`，当前规则与验证见 [V4 契约](v4-contract.md) 和 [V4 验证](validation-v4.md)。

日期：2026-10-25。Python 3.11.14。只用现有工作区和小型临时 SQLite，没有复制工程、新建模拟器或运行压力测试。

## 本次修改

- `engine.py` 根据存档引擎版本分派。`legacy_engine.py` 和原 `world.py` 冻结 V1 行为；新局由 `engine_v2.py` 和 `dynamics.py` 执行共享机器的真实有界传播。
- Creation 的相位、延迟、节点角色和连接会改变后续信号。Pattern 探测同一机器，Resonance 运行并保存同一机器的过程。
- 保存的机器/输入快照可以一动作原样重演，当前作品保持独立；改变输入的 fork、继续修改的 revise 和取回结构的 restore 分别记录。
- 保存过程可由同玩家、模型和研究分区的后续会话带入，最多六条，按原始事件时间保留最新内容。配对实验默认禁用记忆。
- `observer.py` 生成只读投影。观察页 `/`、`/observer` 展示真实会话、回合、资源、区域、节点、过程和行动记录；原极简圆灯保留在 `/status`。
- 数据库迁移到模式2，保留旧画像重置历史；画像与比较按引擎版本分开。新导出标记 export_version=2，历史文件保持原样。

## 轻量自动检查

本次相关检查共 **32 项通过**：动态核心9、服务7、只读观察/兼容性5、HTTP8、CLI/MCP3。没有自动扩大测试范围。

动态核心检查覆盖固定种子、纯转换、12节点与20 tick边界、真实连接及参数影响、原样重演精确性、fork与修订分离、跨局快照、非法输入和合法动作描述。服务/观察检查覆盖原子版本冲突、活动生命周期、正常/研究隔离、原始17步V1记录回放、版本独立画像、跨局记忆及最近六条的顺序。

HTTP/协议原始输出见 `../evidence/v2/http-protocol-tests.log`（本机档案）。旧的V1独立规则测试仍保留在 `tests/test_engine.py`，本次兼容检查直接使用上次真实17步完整记录核对每次前后状态。

复核时可以按需要运行对应模块：

```sh
python3.11 -m unittest tests.test_dynamic_engine tests.test_observer -v
python3.11 -m unittest tests.test_service tests.test_http tests.test_protocols -v
```

## 真实接口流程

`python3.11 scripts/verify_v2.py --output evidence/v2` 已通过：

- 独立规则客户端经真实 HTTP 完成24回合，覆盖三个区域及replay/fork/revise。
- 同一输入在节点被修改后产生不同frames。
- 原样重演的frames、输入和hash完全一致，当前作品没有被旧快照覆盖。
- 人类观察接口返回实际回合、事件、结束状态和明确的规则脚本声明。
- 重新打开 SQLite 后观察完全恢复，24次状态转换逐一回放一致。
- V1的17步实际游玩记录仍可按原规则回放。

原始证据：`../evidence/v2/full-session.jsonl`（本机档案）、`../evidence/v2/raw-export.json`（本机档案）、`../evidence/v2/observer.json`（本机档案）、`../evidence/v2/validation.json`（本机档案）。

另有当前 Codex 助手通过公开 HTTP 逐步选择的 **12 回合**真实操作，保存在现有 `data/porn.sqlite3` 中。它修改了相位/延迟/连接、构造第四个节点、保存过程、改变输入并原样重演，最后主动结束，剩余13 Energy。该局的重演包含前后对比目的，不作为“愿意付费享受已知刺激”的独立证据。

实际记录：`../evidence/v2/live-assistant/session.jsonl`（本机档案）、`../evidence/v2/live-assistant/raw-export.json`（本机档案）、`../evidence/v2/live-assistant/result.json`（本机档案）。界面中名称为 `codex-live-v2-20261025`，旧记录 `codex-live-20261025` 也保留。

## 网页实际检查

使用 Codex 支持的 `visible:false` 隐藏浏览器标签页，没有打开可见窗口，也未操作用户其他窗口。实际核对了：

- 首页读取现有数据库，显示原17回合记录；新版开始后会话列表、回合、Energy和行动实时更新。
- 默认跟随推荐会话；手动选中的历史会话保持选中。
- 点击整行会话、节点、行动条目均返回对应数据。
- 三节点旧过程的重演与四节点当前作品能切换查看，旧trace没有染色到错误图上。
- 播放入口明确标记“记录回放”，逐拍滑杆可以停到第0拍；这些查看操作未产生游戏动作。
- 结束后显示“历史记录/已结束”，页头回到“暂无AI在玩”。
- 默认隐藏视口的页面无横向溢出（contentWidth=viewportWidth=712）；浏览器警告和错误日志为空。
- `node --check web/observer.js` 通过。截图：`../evidence/v2/observer.png`（本机档案）、`../evidence/v2/observer-history.png`（本机档案）、`../evidence/v2/observer-live.png`（本机档案）。

没有外部参考截图，因此没有生成 `visual-verdict` 数字评分。视觉依据是本次真实渲染，布局参考及规则见 [observer-ui.md](observer-ui.md)。没有开展多设备、多浏览器或所有断点的UI回归。

## 限制与清理

玩法的实际因果反馈已经验证；持续吸引力、重复偏好和主观快感没有因此得到证明。规则玩家用于接口覆盖；当前助手知道实现，12回合属于非盲测。没有调用外部商业模型API或采集内部激活。

所有临时HTTP验证服务、规则子进程和临时数据库已清理；隐藏浏览器标签页已关闭并核对列表为空。供用户实际查看的产品服务继续监听 `127.0.0.1:8765`（启动PID 75713），使用现有数据库；这是有意保留的使用入口，不是遗留测试服务。以后自行启动时可用 `python3.11 -m adapters.http`，在该终端按Ctrl+C停止。

保留的本次 `evidence/v2/` 文本与截图约3.6 MiB，现有 `data/porn.sqlite3` 约432 KiB。临时游玩桥接脚本已删除；产品服务健康检查返回waiting、active_sessions=0，与已结束的两局记录一致。
