# Story Canon and StoryState v0.1

## 1. Vertical Slice

`story_after_the_show_001`（《散场之后》）是第一个 Narrative Runtime
vertical slice。一次南栈小型商业与社区联合演出正常结束后，观众离场与临时撤场动线在共享窄点冲突。事故造成短时拥堵和一名撤场工作人员轻度踝部扭伤，没有能力暴走、阴谋或重大城市危机。

这段 Canon 自然建立：

- `incident_nanzhan_postshow_route_conflict_001`
- `case_nanzhan_postshow_coordination_001`

Incident 是已经发生的具体事故；Case 是事故后事实核对、费用、流程责任与整改协调的具体工作单元。两者拥有不同 ID、不同 active set 和不同 assignment map，不能互换。

## 2. Layer boundaries

`data/stories/story_canon.yaml` 保存客观、instance-level Story 事实，并为本轮 Case / Incident 提供 `story_refs` 证据。Case / Incident 中的 generic `lore_refs` 只说明制度背景，不声称旧 Lore 已经描述本次事故。

`data/stories/story_definitions.yaml` 保存节点、合法 transition 和白名单 effects，回答“这段剧情如何推进”。

`StoryState` 保存单次 playthrough 的当前位置、已完成节点、active Case / Incident、明确的角色运行时 assignments 与 flags，回答“这次推进到了哪里”。它不保存静态角色身份、Canon 内容或权限结论。

## 3. Deterministic runtime

Story v0.1 是六节点单线图。相同 StoryDefinition、initial state 和 transition sequence 必须产生语义相同的 StoryState。Runtime 不使用 LLM、随机数、网络或任意代码执行。

允许的 effects 只有：

- `activate_incident`
- `activate_case`
- `assign_character_to_incident`
- `assign_character_to_case`
- `unassign_character_from_incident`
- `unassign_character_from_case`
- `set_story_flag`
- `complete_node`

Effect payload 使用严格字段白名单。错误 current node、unknown transition、unknown reference、向 inactive 对象赋值或 permission-like flag 都产生明确 Domain Error。

Assignments 使用集合语义；重复 assign 不会产生重复值。每次 transition 返回新 StoryState，不原地修改输入。

## 4. Serialization and restore

`StoryState.to_dict()` 对集合和 mapping keys 做稳定排序。`StoryRuntime.restore()` 通过严格 schema 恢复并重新验证 Story、Node、Case、Incident、Character 和 active-assignment invariants。未知字段不会被静默保留。

这个 round trip 为未来 Save System 与 Agent Memory 提供确定性基础，但本轮没有实现这些系统。

## 5. Runtime Assignment is not Character Identity

唐栖在 Case 建立后得到 runtime case assignment；纪衡得到有限的 onsite incident assignment。两者都不会回写 `characters.yaml`。余弦是舞台工作人员和 witness，但 witness 不等于 Incident 或内部复盘 assignment，因此她不会从 StoryState 获得 `active_incidents`。

主角存在于 Narrative，并随委托参与初步事实整理；当前不创建第八个 Character，也不伪造 player character ID。Player Identity Integration remains future work。

## 6. Knowledge trust boundary

`KnowledgeContextProvider` 只做两项映射：

- character Case assignments → `KnowledgeContext.active_cases`
- character Incident assignments → `KnowledgeContext.active_incidents`

Provider 不从 occupation、faction、tags、witness 或 story flags 推断 role、responsibility、authorization、project 或权限，也不返回 ALLOW / DENY。

纪衡即使拥有本次 `active_incidents`，仍不具备 knowledge_rule_027 所需的 division_015、`department_training` 或 `incident_professional_lead` Subject，因此访问 `lore_027` 仍然 DENY。他的现场 assignment 也没有被 Canon 为该 Lore 的内部复盘 assignment。

唐栖即使拥有本次 `active_cases`，仍不具备 knowledge_rule_005 所需的 faction/division Subject；本 Case 也没有被纳入 Lore 005 的跨行业能力评级研究语料，因此访问 `lore_005` 仍然 DENY。

StoryState 拒绝 `allow_lore`、`grant_knowledge`、`can_access`、`permission`、`authorization`、`responsibility`、`role` 和 `project` 等权限或静态身份字段。LLM 与 caller 都不能通过 StoryState 直接决定访问权。

## 7. Ability boundaries

事故直接原因是时间交接和路线分离失败，不是能力暴走。余弦只在人员停止继续涌入后用现实参照点帮助等候与引导，没有强迫移动。纪衡只在伤员经现实处置进入可观察、相对稳定状态后配合观察与交接；他的能力没有治疗、恢复损伤或维持抽象“现场秩序”。

## 8. Knowledge Scope impact

本 Story 新增的 Case / Incident 与 Lore 005、022、027、032 所述对象都没有 Canon 同一关系。相关 scope bindings 继续 unresolved，values 保持为空。Coverage 仍为 9 / 32（28.12%）；coverage 不是 KPI。

## 9. Deferred work

本轮没有实现 NPC / Quest Agent、Belief、Rumor、RAG、Embedding、Vector DB、branching narrative、dialogue、Player Identity、Agent Memory 或 LLM planning。Case 的最终责任裁定和后续完整流程也留给未来 Story slice。
