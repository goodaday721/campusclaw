# 产品设计规范

适用范围：教师端与学生端的页面、文案、状态与视觉。每条规则都必须能在 `app/routes/pages.py` 或对应接口响应里找到落点。

## 用户与场景

- 教师：登录 → 上传本班材料（`.txt`/`.md`）→ 检索验证切片效果 → 配置班级提示词、引导技能、智能体 → 登记并连接 MCP 工具服务器 → 查看本班调用记录。
  检查：README「解题助手智能体」「MCP 工具服务」两节的验证路径逐条走通；`docker compose exec -T api python e2e_test.py` 通过。
- 学生：登录 → 浏览并下载本班材料 → 检索本班切片 → 一次性问答 → 在解题助手会话中向已启用智能体提问（流式，带出处与工具状态）。
  检查：`tests/test_materials.py::TestDownload`、`tests/test_retrieval.py::TestAsk`、`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow`。

## 页面与路由清单

| 路由 | 用途 | 角色 |
|---|---|---|
| `/login` | 登录页；成功后写 `localStorage.cc_token` 并跳 `next`（默认 `/dashboard`） | 匿名 |
| `/dashboard` | 唯一工作台：材料、检索、问答、解题助手、教师配置卡、MCP 卡 | 登录 |
| `/swagger/index.html` | Swagger UI；Authorize 填登录返回的 token 后在线试调 | 匿名页面，接口需 token |
| `/`、`/me` | 302 跳 `/dashboard` | 匿名 |
| `/openapi.json` | OpenAPI 3.0.3 描述 | 匿名 |

- 新增页面必须先在本表登记，再在 `pages.py` 加路由。
  检查：`grep -n '@pages_bp.route' app/routes/pages.py` 与本表逐行对应。

## 视图四状态模板

| 视图 | 加载中 | 正常 | 错误 | 空状态 |
|---|---|---|---|---|
| 材料列表 | 加载中... | 文件名 + 上传者 + 大小 + 下载 | 加载失败 | 暂无材料 |
| 检索结果 | 检索中... | 命中卡：标题、#切片、字符区间、摘录、打开材料 | 检索失败: <error>；503 追加「（向量/网关暂不可用，可改用关键字检索）」 | 资料中未找到相关内容 |
| 问答 | 思考中... | 回答正文 + `[n]` 出处链接 | 问答失败: <error>；503 追加「（模型网关暂不可用）」 | 固定文案「资料中未找到相关内容」，无出处 |
| 会话列表 | 加载中... | 会话标题 + 智能体名 | 加载失败 | 还没有会话（点击上方"+ 新会话"）/ 暂无可用智能体 |
| 对话区 | 思考中... | 气泡 + 技能标签 + 工具状态栏 + 出处 | 发送失败: <error> | 选择或新建会话后开始提问 |
| MCP 服务器 | 加载中... | 名称 + 连接状态 + 令牌标记 + 工具清单 | 加载失败 | 本班尚未登记 MCP 服务器 |
| 调用记录 | 加载中... | 工具@服务器 + 状态徽章 + 用户/会话/轮次/时间 | 加载失败 | 暂无调用记录 |

- 四态文案必须与 `pages.py` 内联字符串一致，不得自创同义文案。
  检查：`grep -n "加载中\|加载失败\|暂无材料\|资料中未找到相关内容\|暂无调用记录" app/routes/pages.py`。
- 流式中途断开显示「（回答中断）」，该轮不落库、不提示成功。
  检查：`app/services/chat.py::sse_stream` 仅在发 `done` 前落库；`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow` 断言末事件为 `done`。

## 术语表

| 术语 | 定义 | 代码落点 |
|---|---|---|
| 智能体 | 教师配置的问答角色，绑定启用的技能与限定材料范围 | `agents`、`agent_skills`、`agent_materials` |
| 技能 | 单段 source 文本（名称/适用条件/工具/资料/启用 + 空行后的引导正文）解析出的引导规则 | `skills`、`app/services/skill_source.py` |
| 材料 | 教师上传的 `.txt`/`.md` 文件及其正文 | `materials`、`knowledge_entries.content` |
| 切片 | 材料正文按 auto/custom/hierarchy 切出的检索单元，带序号与字符区间 | `knowledge_chunks` |
| 引用 | 回答中 `[n]` 标注对应的切片出处（材料标题、切片序号） | `citations` JSON，`ref` 从 1 起 |
| 工具 | MCP 服务器暴露的可调用函数 | `mcp_tools_cache` |
| 服务器 | 教师登记的 MCP 工具服务器（单端点 JSON-RPC） | `mcp_servers` |
| 会话 | 某用户在某班某智能体下的多轮对话 | `conversations`、`messages` |

- 界面出现新名词，先入本表再写文案。
  检查：`grep -n "智能体\|技能\|切片\|工具\|服务器\|会话" app/routes/pages.py` 逐一对照本表。

## 表单与校验时机

- 前端只拦空输入与类型（`required`、`accept=".txt,.md"`），提交瞬间禁用按钮并改文案（上传中...、回答中...）防重复提交。
  检查：`grep -n "btn.disabled\|sendBtn.disabled\|accept=" app/routes/pages.py`。
- 服务端是唯一裁决：同一规则在 routes 或 services 再校验一次，返回 400/409/413/415 的可读 `error`。
  检查：`tests/test_materials.py::TestUploadConstraints`、`tests/test_mcp.py::TestRegistryAPI::test_create_duplicate_409`。
- 列表类错误就地写进对应 `.err-msg`（检索失败、问答失败、发送失败）；单条操作用 `alert('<动作>失败: ' + 状态)`；仅删除类操作使用 `confirm` 二次确认。
  检查：`grep -n "alert(\|confirm(\|errEl.textContent" app/routes/pages.py`；`tests/test_assistant.py::TestSkillsAPI::test_create_bad_source_400`、`tests/test_assistant.py::TestPromptAPI::test_put_empty_body_400`。

## 视觉基线

- 主色北大红 `#94070a`；悬停 `#78050a`；浅红 `#b8302f`；金色 `#c5a572` 仅用于角色徽标；页面底 `#f5f3f1`；正文 `#2b2b2b`。
  检查：`grep -n "pku-red:\|pku-red-dark:\|pku-red-light:\|pku-gold:" app/routes/pages.py` 取值与本条一致。
- 字号层级：品牌 18 / 卡片标题 16 / 列表主名 15 / 正文 14 / 辅助 13 / 元信息 12 / 标签 11（px）。
  检查：`grep -n "font-size: 18px\|font-size: 16px\|font-size: 15px" app/routes/pages.py` 分别落在 `.brand`、`.card-header`、`.material-item .name`。
- 间距刻度 4 / 6 / 8 / 10 / 14 / 18 / 22 / 28 px；容器最大宽 900px，卡片圆角 10px，按钮圆角 4px。
  检查：`grep -n "max-width: 900px\|border-radius: 10px\|margin: 28px" app/routes/pages.py` 三处均命中。

## 状态与流程

- MCP 服务器 `status`：`disconnected` 允许连接/编辑/删除，引用保存返回 400、被调用记 `denied`；`connected` 允许断开/重连/删除。
  检查：`tests/test_mcp.py::TestRegistryAPI`、`tests/test_mcp.py::TestSkillReferenceValidation`。
- 智能体 `enabled`：1 学生可见并可建会话；0 时学生建会话 404（提问走同一可见性校验），教师仍可编辑。
  检查：`tests/test_assistant.py::TestConversationsAPI::test_create_with_disabled_agent_student_404`。
- 技能 `enabled`：1 整段注入提示词且可被绑定；0 不注入、学生不可见。
  检查：`tests/test_assistant.py::TestSkillsAPI::test_student_sees_enabled_only`。
- 会话无状态列，只有 `created_at`/`updated_at`；未收到 `done` 的轮次视为未完成。
  检查：`migrations/004_assistant.sql` 的 `conversations` 定义与本条一致；`tests/test_assistant.py::TestConversationsAPI::test_sse_hit_flow`。
