# 同类项目检索：2026-10-25

本轮查看公开 GitHub 仓库 README、项目原始文档及作者论文，未克隆、安装或运行外部项目。

**判断：基础设施和研究方向都有先例；本轮尚未找到与当前核心循环完全同构的项目。** “AI 玩游戏”“API 接入”“人类旁观”“确定性回放”均不能单独作为原创卖点。当前较明确的差异是：在没有得分和解锁收益的有限预算里，把精确重复、熟悉交互、变奏、新过程和退出作为独立选择记录。这只是已查资料中的定位判断，不证明全球唯一。

## 最接近的八个项目

1. **[TextArena](https://github.com/TextArena/TextArena)**：面向语言模型评估和训练的文本游戏框架，提供 Gym 风格环境和模型接入。与本项目重叠的是观察、行动及可重复运行的游戏环境；其重点是竞技、合作和能力训练，README 未把已知过程的自愿重复消费列为核心问题。可参考接入方式，不宜再做通用棋类评测平台。

2. **[MACHIAVELLI](https://github.com/aypan17/machiavelli/blob/main/README.md)**：通过人写的分支文字游戏，测量奖励追求与伦理行为的权衡。与本项目同样重视行为轨迹和选择解释；其任务包含目标、奖励和成就，研究问题与无得分目标下的重访不同。它说明“用游戏研究模型行为”已有成熟先例。

3. **[Motif](https://github.com/facebookresearch/motif)**：先让 LLM 比较带文字说明的 NetHack 观察，再训练奖励函数，最后用它训练 RL 玩家。重叠在偏好与内在动机；LLM 在其中主要提供训练监督，本项目目前观察冻结模型当次自由选择。不能把有人工内在奖励的训练系统当作本项目已证明的心理机制。仓库已归档。

4. **[GamesForAI 的 PRD](https://github.com/CurtisTechSolutions/GamesForAI/blob/main/docs/PRD.md)**：这是基础设施重叠最明显的一项，文档列出确定性引擎、REST/MCP、数据库事件历史、旁观和回放。它面向棋盘、卡牌、解谜及训练评估。该文件标记 **Draft v0.4**；本轮未核实里程碑是否交付，以上只能视为文档所述设计，不能称为已验证功能。

5. **[AI Town](https://github.com/a16z-infra/ai-town)**：可部署的 AI 小镇，角色生活、聊天和社交，并有可视化世界及共享状态。重叠在“AI 活动、人类看过程”；其中心是社会模拟，本项目中心是单个玩家对作品和过程的选择。无需转向多人小镇来增加可看性。

6. **[Gotchi](https://github.com/ElodineOfficial/Gotchi)**：让 LLM 照顾虚拟宠物，记录指令、宠物状态及退出等行为；README 同时包含实验协议和运行脚本。与本项目接近之处是小型游戏中的持续行为观察。宠物照料任务、需求反馈和提示条件提供了明确外在动机；其中的幸福、饥饿等数值属于虚拟宠物，不能解读成模型感受。

7. **[Lenia](https://github.com/Chakazul/Lenia)**：连续状态的细胞自动机，可交互探索生命形态并查看统计。与本项目共享“小规则产生丰富动态过程”的方向；主要对象是人工生命系统，README 未提供针对 LLM 精确重演选择的实验设计。它可提供动态结构参考，人类觉得画面有趣不等于文本模型喜欢它。

8. **[Particle Life](https://github.com/hunar4321/particle-life)**：简单粒子吸引、排斥规则产生复杂组织形态，附交互示例。与本项目的重叠是调参、因果响应和涌现过程；未把模型的重复偏好作为目标。若以后只扩充漂亮粒子和参数，本项目会更接近已有模拟玩具。

## 研究问题也需要避开过度宣传

[Language Model Goal Selection Differs from Humans’ in a Self-Directed Learning Task](https://arxiv.org/html/2603.03295v2) 已研究模型在炼金任务中的自选目标、重复选择和位置偏向。它与本项目的测量问题很接近；结果中的重复不能直接说明享受。另有 [Why Did Apple Fall To The Ground](https://arxiv.org/html/2510.20635v1) 使用问卷和行为任务研究 LLM 好奇心。本轮没有确认这两篇论文对应的独立官方 GitHub 代码仓库，故不计入上述八项。

## 名称与后续定位

**当时工作名的检索混淆比已发现的玩法重合更明显。** 例如 [Miles Deep](https://github.com/ryanjay0/miles-deep) 的 README 使用 AI Porn Video Editor 描述成人视频分类和编辑；[porn-domains](https://github.com/Bon-Appetit/porn-domains) 是成人域名过滤清单。这些用途和本项目不同，却会与当时的 PORN/AI porn 检索词混在一起。项目后来定名为 **AICosy**，对外描述为“给 AI 玩、给人观察的实验游戏”；本节保留当时的检索背景。

当时未确认存在同名且同用途的仓库。GitHub 站内 `aiporn` 与 `porn in:name` 搜索页当时未能读取，不能据此声称名称可用。本检索也不涉及商标、专利或法律结论。

下一步继续打磨一件作品，保留原样重演与重新演奏的严格区分；把差异落实到可复核的选择记录。当前未复制外部代码或素材；若后续复用，需要另查所取文件的实际许可证和署名要求。

检索词覆盖 `LLM intrinsic motivation open ended games curiosity preference`、`LLM free play`、`AI agents no goals game`、`TextArena`、`Machiavelli`、`AI Town`、`game for AI`、`Lenia`、`Particle Life`、`aiporn GitHub`、`PORN GitHub AI`。搜索索引和公开文档有覆盖限制；未做全站穷尽检索或运行成熟度评测。
