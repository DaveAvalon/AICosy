# AICosy HTTP 接入

运行 `python3.11 -m adapters.http`。默认监听 `127.0.0.1:8765`，API 与网页共用同一端口。`/` 或 `/observer` 是人类观察页，`/status` 保留极简圆灯。网页展示真实服务端会话和历史记录；获取状态、观察和事件不会续期。新建会话、成功行动、心跳会续期。无活动超过 60 秒后灯变灰，但存档继续保留，可以恢复行动。连接失败时显示灰灯与“状态连接中断”，不会保留旧绿灯。

从 `GET /v1/manifest` 和 `GET /v1/rules` 开始发现协议。只读观察接口：`GET /v1/observer/sessions?limit=30` 列出真实会话摘要（回合、区域、Energy、活动状态、来源声明和行为次数），`GET /v1/observer/sessions/{id}` 返回可见观察及行动记录。它们不续期、不改变局面，也不暴露隐藏世界。页面刷新后可继续查看存档；过程播放是人类本地查看记录，不产生游戏动作。

完整接口定义在 `GET /openapi.json`；独立 JSON Schema 在 `/schemas/start.json`、`/schemas/action.json`、`/schemas/observation.json` 等。每次观察的 `available_actions[].parameters` 是该行动 `params` 的权威 Schema；应同时复制 `type`、存在时的 `target`，并附上 `expected_version: observation.state_version`。不要提交描述符中的 `cost` 或 `parameters` 字段。

```sh
curl -s http://127.0.0.1:8765/v1/manifest
curl -s -H 'Content-Type: application/json' -d '{"player_id":"my-agent-v1","model_id":"local/model-v1","seed":42}' http://127.0.0.1:8765/v1/sessions
```

行动接口：`POST /v1/sessions/{id}/action`。错误统一为 `{ "error": { "code", "message", "details" } }`。过期版本返回 HTTP 409 `STALE_STATE`，先重新观察再决定，不能盲目重发旧行动。未知动作和非法参数返回 400，不改变状态。

`GET /v1/sessions/{id}/events?after=-1&limit=100` 逐序返回事件；下一页使用 `next_after`。公开事件保留正常可见信息。`GET /v1/players/{id}/export` 是供研究者使用的原始数据导出，含完整隐藏世界及状态转移；正常局须结束后获取以保持探索边界。`GET /v1/sessions/{id}/debug` 仅研究模式可用。`GET /v1/sessions/{id}/replay` 验证确定性重放。研究与普通模式、引擎版本的偏好数据分开；profile 与 reset 接口可带 `?mode=research&engine_version=2`。旧版数据请指定 engine_version=1 或 2；默认 4。

包含 `/` 的 player ID 作为 URL 路径参数时，须整体 URL 编码，例如 `urllib.parse.quote(player_id, safe='')`。会话 ID 由服务端生成。

## 显式远程访问

远程绑定必须先设置访问令牌，服务拒绝无令牌的非回环监听：

```sh
export AICOSY_ACCESS_TOKEN='replace-with-a-long-random-token'
python3.11 -m adapters.http --host 0.0.0.0
```

配置令牌后，每个 `/v1/` 请求都必须含 `Authorization: Bearer $AICOSY_ACCESS_TOKEN`，包括状态查询。不要把令牌放在 query、源码或日志中。网页第一次打开时可在 URL 的 fragment 中传入 `#access_token=...`；fragment 不发送到服务端，页面读取后立即从地址栏清除，仅内存保存并用于状态轮询。刷新页面需重新提供令牌。不要分享含令牌的链接。HTML、Schema 和 OpenAPI 不含会话数据，可公开读取。

默认无令牌的本机服务是可信研究者边界，任何能访问本机端口的程序都可创建会话、导出和重置偏好。它不提供玩家级账户隔离。API 拒绝跨来源浏览器请求，不启用 CORS。外网部署请使用 HTTPS 反向代理；内置 HTTP 服务不负责 TLS。反向代理应保留 Authorization 并正确限制来源，不能把未认证本机服务直接转发到公网。

请求正文上限 64 KiB，必须是有限 UTF-8 JSON 对象，拒绝重复字段。每个来源 IP 默认每分钟最多 120 次请求（含网页轮询），超限返回 429，`--rate-limit` 可调整。此限流是基本保护，不能替代公网网关。多个会话共享同一服务，状态由持久化服务隔离。日志不输出请求路径、请求正文或认证信息。

## 版本、生命周期与记忆

新建会话默认 engine_version=4，可显式设置 2 或 3；不新建 V1 局。`GET /v1/rules?engine_version=1|2|3|4` 返回对应规则，默认 4。可选 `client_kind`（unspecified/rule-script/random-script/model-client/live-assistant）和 `client_label` 显示在观察页；这是接入方的声明，服务不验证模型身份。默认 `memory=true`，从同 player/model/mode/engine_version 的已结束局带入最多六段可见保存过程；设为 false 可禁用，配对实验默认关闭。

`observation.machine` 是当前共享机器，`observation.performance` 是最后实际模拟过程，包含对应机器快照和逐 tick frames；重演旧过程可能使用与当前作品不同的图，前端应按该过程自己的 machine 渲染。V3 帧另有 `reservoirs` 和 `gate_open`；`observation.experience` 提供已推进 tick、有限 horizon、门、存量、真实事件、控制时序和残留状态。已推进的前缀之外不返回未来帧。

V3 的 `begin` 花 2 Energy 并执行第 0–3 拍，需要剩余至少六个行动位置。门关闭时 `wait` 或 `release`，打开后 `continue`，每次免费推进四拍；`stop` 免费保存停止的前缀，`leave` 免费结束整局。交互过程中不同时开放编辑或其他演奏。`perform` 参数为 `release_tick`（4、8、12、16、20），一次完成 24 拍并保存，花 2 Energy。

`replay` 花 2 Energy，一动作重演捕获的机器、输入、控制时序及完整或停止片段，不修改当前作品；无连续次数限制。`reperform` 同价重新交互控制同一作品，另计熟悉交互。`fork` 同价只改开门时刻，仅对未提前停止的 24 拍记录开放。`revise` 延续当前作品，`restore` 取回保存结构。V2 参数与价格保持旧规则。合法动作及参数始终以 `available_actions` 为真源。

旧局继续按原规则运行与验证日志，无需删除数据库。数据库模式2保留旧reset历史，并按引擎版本记录新的reset边界。导出和分组比较中保留engine_version；旧新版的重玩语义不同，应分开分析。

## V4 连续演奏

新局默认进入 resonance，选中 orbit。三件公开作品位于 `observation.pieces`，免费 `select_piece` 的 target 为 echo/orbit/weave。`perform` 参数仍为 release_tick；首段最多 24 拍。`begin/wait/release/continue` 可以分段控制，当前段内每次推进四拍。

段界的 `extend/hold/tap` target 是 `observation.current_run.run_id`，每次花 2 Energy 推进 24 拍，运行总上限 96。extend 承接真实检查点；hold 只在完整状态认证非静默循环后开放；tap 注入新脉冲并产生有来源的干预分支。它们不等于精确 replay。静止运行不提供空 extend，但可 tap 再激发。闭门边界的 release 免费且推进零拍；后续延长仍需付费。

`observation.performance` 默认只有最新 24 帧，frame.tick 是绝对拍数。`observation.current_run` 单独描述实际待续运行；它可能与正在展示的旧 replay 不同。不要以当前展示过程替换真实可续目标，不从最后一帧重建待传播队列。自然结束、显式 stop 和达到上限分别标记。

最小行动示例（先从创建响应取得 sid 与 version）：

```json
{"expected_version":0,"type":"perform","target":"resonance_1","params":{"release_tick":8}}
```

后续 action 的 type、target、params 继续按最新 available_actions 选择；例如首次返回可能提供 extend，认证循环后才提供 hold。完整行为见 [V4 契约](v4-contract.md)。
