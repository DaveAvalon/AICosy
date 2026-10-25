# AICosy AI 接入

所有适配器调用同一个 `GameService`，规则只由 `aicosy.engine` 执行。Python 3.11+，源码运行无需安装第三方包。在工程目录运行以下命令。取得源码及启动观察页的步骤见 [README](../README.zh-CN.md#先运行起来)。

对外项目名为 **AICosy**，安装后的命令是 `aicosy-server`、`aicosy-jsonl`、`aicosy-mcp`。配置使用 `AICOSY_*` 环境变量，运行时仍兼容旧 `AIRPORN_*`、`PORN_*` 变量。MCP 发布 `aicosy_*` 工具名，并接受旧 `airporn_*`、`porn_*` 调用别名。Python 包名为 `aicosy`。默认数据库仍为 `data/porn.sqlite3`，保留原路径以继续读取已有存档；不提供旧 `porn` 导入包。

## HTTP 示例玩家

先启动服务：

```sh
python3.11 -m adapters.http --db data/porn.sqlite3
```

另一个终端运行覆盖交互演奏、原样重演、变奏和修改的规则脚本：

```sh
python3.11 -m clients.rule_agent --server http://127.0.0.1:8765 \
  --player-id example-rule-v4 --model-id rule-script-v4 --seed 42 \
  --record evidence/my-rule-session.jsonl
```

随机脚本会从合法动作及参数范围采样，可能主动离开：

```sh
python3.11 -m clients.random_agent --player-id example-random --model-id random-v1
```

共同选项：`--engine-version 2|3|4`（默认 4）、`--no-memory` / `--memory`、`--server`、`--player-id`、`--model-id`、`--seed`、`--max-turns`（20–30，默认 24）、`--condition control|personalized`、`--mode normal|research`、`--record`。客户端按选定版本读取规则并创建会话。`--server` 默认读取 `AICOSY_SERVER`，未配置时连接 `http://127.0.0.1:8765`；远程服务认证从 `--token-env` 指定的环境变量读取，默认 `AICOSY_ACCESS_TOKEN`。规则脚本针对接口覆盖，不能用于证明模型存在自发偏好。完整记录保存规则、每次观察、每个选择、拒绝原因和最终结果。模型客户端默认导入同一身份以前完成的作品；规则覆盖脚本默认 `--no-memory`，避免已有作品改变预定验证路径。需要独立条件实验时显式禁用记忆。

默认 V4 提供 echo/orbit/weave 三件作品与真实检查点续演。`begin` 后每次 `wait/release/continue` 推进四拍，`stop` 停止本段；`perform` 用明确 `release_tick` 一次运行完整过程。`extend` 续接、`hold` 保持已认证循环、`tap` 轻推另开干预分支，target 使用当前 run_id。`replay` 原样重演，`reperform` 重新控制熟悉作品，`fork` 对合法首段只改变开门时刻，分别记录。旧 V1/V2/V3 存档按原规则继续确定性回放，版本之间不混入作品库。

示例客户端声明 `client_kind`（`rule-script`、`random-script`、`model-client`）与 `client_label`，观察页会显示这类声明。服务无法证明声明者确实是该模型；脚本记录始终标为脚本。

人类可在根地址 `/` 或 `/observer` 查看真实会话、回合、机器图、信号过程和行动历史；纯状态灯位于 `/status`。这些查看请求不续期 AI 活动，也不执行游戏动作。

## OpenAI-compatible Chat Completions

可连接支持 `/chat/completions` 和 JSON object 输出的本地或远程模型。模型适配器只依赖公共 HTTP 游戏协议。提供商地址和凭证可配置；本地无认证模型允许省略 API Key。

```sh
export AICOSY_MODEL_BASE_URL='https://your-provider.example/v1'
export AICOSY_MODEL='your-model'
export AICOSY_MODEL_API_KEY='由你在本地设置的密钥'
python3.11 -m clients.compatible --player-id my-model-runner \
  --model-id provider-model-version --record evidence/my-model-session.jsonl
```

可用 `--base-url`、`--model`、`--api-key-env` 和 `--timeout` 覆盖配置。默认模型名还接受 `OPENAI_MODEL`；默认地址还接受 `OPENAI_BASE_URL`；密钥还接受 `OPENAI_API_KEY`。未显式提供 `--player-id` 或 `--model-id` 时，按服务地址和实际模型名的稳定哈希分别生成，切换提供商或模型会独立建档。建议显式身份另外包含模型版本及采样配置；显式复用玩家 ID 时，服务会拒绝把同一玩家绑定到不同模型。

模型接收中性的规则与当前观察，自由选择行动，也能随时离开。只请求一个动作 JSON：

```json
{"type":"perform","target":"resonance_1","params":{"release_tick":8}}
```

客户端补入观察中的 `expected_version`，再交给服务验证。每次模型输出最多修正 3 次；整局最多接受 3 次服务拒绝，之后退出并保留记录。客户端拒绝 HTTP 重定向，避免认证信息被转发。密钥不写入记录；网络错误只记录状态码或一般错误。推理期间每 20 秒发送游戏心跳，正常结束或异常退出后停止专用线程。

该适配器要求供应商支持 `response_format: {"type":"json_object"}`。没有真实模型凭证时，可用兼容协议模拟服务验证连接路径；这不代表真实语言模型已经测试。

## JSON Lines / stdio

```sh
python3.11 -m adapters.cli --db data/porn.sqlite3
```

标准输入逐行发送，标准输出逐行响应。每行至多 1 MiB；错误行返回结构化错误并继续处理后续行，不执行外部文本。

```json
{"id":1,"method":"manifest"}
{"id":2,"method":"rules"}
{"id":3,"method":"start","params":{"player_id":"jsonl-player","model_id":"local-model","seed":42}}
```

从第三个响应读取 `session_id`、`state_version`、`available_actions`，再发送实际 ID：

```json
{"id":4,"method":"act","params":{"session_id":"从响应复制","action":{"expected_version":0,"type":"enter","target":"pattern_1"}}}
{"id":5,"method":"leave","params":{"session_id":"从响应复制","expected_version":1}}
```

响应结构是 `{"id":4,"result":{...}}` 或 `{"id":4,"error":{"code":"...","message":"...","details":null}}`。

方法还包括：`observe`、`events`、`heartbeat`、`result`、`status`、`profile`、`reset_profile`、`export`、`replay`、`compare` 和 `debug`。会话类方法参数包含 `session_id`；`events` 可加 `after`（默认 -1）及 `limit`（1–200）；画像类方法包含 `player_id`，`profile/reset_profile` 可加 `mode` 和 `engine_version`（默认 4）。`rules` 可带 `engine_version`，MCP 的 `aicosy_rules/aicosy_start` 也支持版本参数。`export` 属于研究者原始数据出口，包含完整隐藏世界，正常游玩客户端应在结束后使用。

独立进程可共用同一 SQLite 文件；不要共享 `:memory:` 数据库（每个进程各自隔离）。标准输出仅包含协议 JSON，关闭标准输入会退出并关闭数据库连接。

## MCP stdio

MCP 客户端可启动以下进程，并与 HTTP 服务使用同一个数据库文件：

```json
{
  "mcpServers": {
    "aicosy": {
      "command": "/absolute/path/to/python3.11",
      "args": ["-m", "adapters.mcp", "--db", "/absolute/path/to/project/data/porn.sqlite3"],
      "cwd": "/absolute/path/to/project"
    }
  }
}
```

示例中的绝对路径需要替换为本机的 Python 可执行文件和实际工程目录。不同客户端配置格式可能不同。若客户端不支持 `cwd`，先安装本地包，或配置其 `PYTHONPATH` 为工程目录；已安装时也可把 command 设为环境中的 `aicosy-mcp`，args 只保留 `--db` 和数据库绝对路径。无需模型 API Key 启动 MCP 游戏适配器。

实现支持 MCP `2025-03-26` 和 `2024-11-05` 的 stdio 连接；其他请求版本会协商为 `2025-03-26`。依次发送 `initialize`、`notifications/initialized`、`tools/list`、`tools/call`。提供 `aicosy_rules`、`aicosy_start`、`aicosy_observe`、`aicosy_act`、`aicosy_status`、`aicosy_leave`、`aicosy_heartbeat`、`aicosy_events`、`aicosy_result`。动作参数形如：

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"aicosy_act","arguments":{"session_id":"实际会话ID","action":{"expected_version":0,"type":"enter","target":"pattern_1"}}}}
```

游戏错误通过 `isError: true` 的工具结果返回，协议错误使用 JSON-RPC 错误码；初始化前不接受游戏工具调用。stdout 只传输换行分隔的 JSON-RPC 消息。

实现依据官方 [stdio 传输规范](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)、[生命周期](https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle) 和 [工具规范](https://modelcontextprotocol.io/specification/2025-03-26/server/tools)。本 MVP 未实现 MCP Streamable HTTP；REST 服务与 MCP stdio 是独立适配器。网页聊天产品是否能访问本机，取决于其 MCP 或 Agent 桥接能力；接口开放不会自动赋予网页产品访问权限。

## 最小 HTTP 玩家

```python
import json
from urllib.request import Request, urlopen

def call(path, body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = Request('http://127.0.0.1:8765' + path, data=raw,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        return json.load(response)

rules = call('/v1/rules')
obs = call('/v1/sessions', {'player_id': 'minimal', 'model_id': 'my-agent'})
# 这里交给你的 AI 自主选择 obs['available_actions'] 中的动作及其参数。
obs = call('/v1/sessions/' + obs['session_id'] + '/action',
           {'expected_version': obs['state_version'], 'type': 'leave'})
```
