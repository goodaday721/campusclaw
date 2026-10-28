# 能力 ↔ Scenario 对照表（自动生成）

由 openspec/specs/ 下 11 个能力主 spec 解析生成，用于第 7 课「能力与场景一一对应」的验收核对。

| # | 能力 | Requirement | Scenario |
|---|---|---|---|
| 1 | api-docs | OpenAPI 接口描述 | 文档可被机器读取 |
| 2 | api-docs | OpenAPI 接口描述 | 需登录端点在文档中标注 |
| 3 | api-docs | 浏览器可用的 Swagger UI | 打开 Swagger UI 并试调 |
| 4 | api-docs | 浏览器可用的 Swagger UI | 未授权试调返回 401 |
| 5 | api-docs | 浏览器可用的 Swagger UI | 学生越权试调返回 403 |
| 6 | api-docs | 浏览器可用的 Swagger UI | 非法入参返回 400 |
| 7 | api-docs | 浏览器可用的 Swagger UI | 不存在的资源返回 404 |
| 8 | api-docs | MCP 管理接口的 OpenAPI 描述 | Swagger 可见可试调 |
| 9 | api-docs | MCP 管理接口的 OpenAPI 描述 | 未授权试调被拒 |
| 10 | api-docs | MCP 管理接口的 OpenAPI 描述 | 学生身份被拒 |
| 11 | api-docs | MCP 管理接口的 OpenAPI 描述 | 不存在的服务器与同名登记 |
| 12 | api-docs | MCP 管理接口的 OpenAPI 描述 | 服务器不可达时连接失败 |
| 13 | api-docs | MCP 管理接口的 OpenAPI 描述 | 文档不含令牌原文 |
| 14 | app-runtime | Docker Compose 启动 | 一键启动后服务可用 |
| 15 | app-runtime | Docker Compose 启动 | 标准启动流程可复现 |
| 16 | app-runtime | 健康检查端点 | 健康检查成功 |
| 17 | app-runtime | 健康检查端点 | 依赖未就绪时降级 |
| 18 | app-runtime | 预置演示数据 | 首次启动预置演示数据 |
| 19 | app-runtime | 预置演示数据 | 种子密码均为哈希 |
| 20 | app-runtime | 预置演示数据 | 重复启动不重复预置 |
| 21 | app-runtime | 敏感配置只来自服务端环境变量 | 缺失必需环境变量时拒绝启动 |
| 22 | app-runtime | 敏感配置只来自服务端环境变量 | 模板不含真实密钥 |
| 23 | app-runtime | 敏感配置只来自服务端环境变量 | 网关未配置时功能降级 |
| 24 | app-runtime | 敏感配置只来自服务端环境变量 | 登出后令牌立即失效 |
| 25 | app-runtime | 敏感配置只来自服务端环境变量 | 签名密钥轮换后旧令牌全部失效 |
| 26 | app-runtime | Compose 重启数据持久 | down 后 up 数据仍在 |
| 27 | app-runtime | Compose 重启数据持久 | down -v 主动重置 |
| 28 | app-runtime | 网络暴露控制 | 仅 web 对宿主机可达 |
| 29 | app-runtime | 网络暴露控制 | web 反向代理转发到 api |
| 30 | app-runtime | 数据库就绪重试 | 数据库晚于 api 就绪时最终启动成功 |
| 31 | app-runtime | 数据库就绪重试 | 重试超限明确失败 |
| 32 | app-runtime | 单实例部署边界 | 文档声明单实例限制 |
| 33 | assistant-chat | 班级提示词管理 | 教师更新班级提示词 |
| 34 | assistant-chat | 班级提示词管理 | 学生修改提示词被拒 |
| 35 | assistant-chat | 技能管理（单段 source 文本） | 教师创建解题引导技能 |
| 36 | assistant-chat | 技能管理（单段 source 文本） | source 缺少引导正文 |
| 37 | assistant-chat | 技能管理（单段 source 文本） | 学生不可写技能 |
| 38 | assistant-chat | 技能管理（单段 source 文本） | 跨班技能不可见不可改 |
| 39 | assistant-chat | 智能体配置 | 教师创建绑定技能与材料的智能体 |
| 40 | assistant-chat | 智能体配置 | 绑定跨班技能被拒 |
| 41 | assistant-chat | 智能体配置 | 学生视图与权限 |
| 42 | assistant-chat | 会话管理与归属隔离 | 学生新建会话并查看 |
| 43 | assistant-chat | 会话管理与归属隔离 | 他人或跨班会话不可见 |
| 44 | assistant-chat | 流式带引用的引导式回答 | 命中资料时流式回答并给出引用 |
| 45 | assistant-chat | 流式带引用的引导式回答 | 无命中不编造 |
| 46 | assistant-chat | 流式带引用的引导式回答 | 关闭技能后回答明显不同 |
| 47 | assistant-chat | 流式带引用的引导式回答 | 未登录与跨班访问 |
| 48 | assistant-chat | 流式带引用的引导式回答 | Nginx 不缓冲流式响应 |
| 49 | class-isolation | 班级作用域绑定会话 | 会话解析出所属班级 |
| 50 | class-isolation | 跨班访问被服务端拒绝 | A 班用户请求 B 班材料列表 |
| 51 | class-isolation | 跨班访问被服务端拒绝 | A 班用户直接请求 B 班材料详情 |
| 52 | class-isolation | 跨班访问被服务端拒绝 | 教师也只能访问本班 |
| 53 | class-isolation | 跨班访问被服务端拒绝 | 跨班下载被拒 |
| 54 | class-isolation | 班级过滤在服务端强制 | 直接构造 URL 越权访问 |
| 55 | knowledge-materials | 教师上传材料写入知识库 | 教师上传成功 |
| 56 | knowledge-materials | 教师上传材料写入知识库 | 上传材料记录归属班级 |
| 57 | knowledge-materials | 教师上传材料写入知识库 | 白名单外类型被拒绝 |
| 58 | knowledge-materials | 教师上传材料写入知识库 | 事务失败无残留 |
| 59 | knowledge-materials | 教师上传材料写入知识库 | 超过大小上限被拒绝 |
| 60 | knowledge-materials | 教师上传材料写入知识库 | 索引失败不影响已提交材料 |
| 61 | knowledge-materials | 本班材料列表可查 | 学生查询本班材料列表 |
| 62 | knowledge-materials | 本班材料列表可查 | 教师刚上传的材料出现在本班列表 |
| 63 | knowledge-materials | 上传写入与班级隔离协同 | 客户端声明的班级被忽略 |
| 64 | knowledge-materials | 本班材料可下载 | 本班学生下载材料成功 |
| 65 | knowledge-materials | 本班材料可下载 | 跨班下载与不存在同构 404 |
| 66 | knowledge-retrieval | 正文切分为切片 | 默认 auto 切分 |
| 67 | knowledge-retrieval | 正文切分为切片 | custom 策略参数边界 |
| 68 | knowledge-retrieval | 正文切分为切片 | hierarchy 按 Markdown 标题分章 |
| 69 | knowledge-retrieval | 正文切分为切片 | 预处理不改写原文 |
| 70 | knowledge-retrieval | 向量嵌入与向量存储 | 切片向量主键与切片一致 |
| 71 | knowledge-retrieval | 向量嵌入与向量存储 | 嵌入失败保留原文且关键字仍可检索 |
| 72 | knowledge-retrieval | 关键字检索 | 原文命中关键字 |
| 73 | knowledge-retrieval | 关键字检索 | 关键字路径不依赖向量库 |
| 74 | knowledge-retrieval | 向量检索 | 语义改写命中 |
| 75 | knowledge-retrieval | 向量检索 | 低相似度候选被丢弃 |
| 76 | knowledge-retrieval | 混合检索与 RRF 融合 | 两路命中同一切片排名更靠前 |
| 77 | knowledge-retrieval | 混合检索与 RRF 融合 | 默认模式为混合检索 |
| 78 | knowledge-retrieval | 检索结果可回溯到原文 | 命中携带完整出处 |
| 79 | knowledge-retrieval | 无依据时不返回结果 | 本班无相关内容 |
| 80 | knowledge-retrieval | 无依据时不返回结果 | 空查询被拒绝 |
| 81 | knowledge-retrieval | 无依据时不返回结果 | 向量库不可用时的降级 |
| 82 | knowledge-retrieval | 检索班级隔离由会话强制 | 请求体伪造班级被忽略 |
| 83 | knowledge-retrieval | 检索班级隔离由会话强制 | 两路均按会话班级过滤 |
| 84 | knowledge-retrieval | 检索班级隔离由会话强制 | 跨班特有词汇检索表现为无命中 |
| 85 | knowledge-retrieval | 教师按新策略重建索引 | 教师重建本班材料索引 |
| 86 | knowledge-retrieval | 教师按新策略重建索引 | 学生不能重建索引 |
| 87 | knowledge-retrieval | 教师按新策略重建索引 | 重建跨班材料被拒 |
| 88 | knowledge-retrieval | 有依据才生成的带出处问答 | 有依据生成带编号引用的回答 |
| 89 | knowledge-retrieval | 有依据才生成的带出处问答 | 无依据不调用生成模型 |
| 90 | knowledge-retrieval | 有依据才生成的带出处问答 | 客户端注入 system 消息被丢弃 |
| 91 | knowledge-retrieval | 有依据才生成的带出处问答 | 学生与教师均可提问 |
| 92 | knowledge-retrieval | 模型网关仅服务端可见 | 浏览器拿不到网关密钥与向量 |
| 93 | mcp-registry | MCP 服务器登记与管理 | 教师登记服务器 |
| 94 | mcp-registry | MCP 服务器登记与管理 | 同名再登记被拒 |
| 95 | mcp-registry | MCP 服务器登记与管理 | 跨班与学生的权限 |
| 96 | mcp-registry | 连接与工具发现 | 连接后发现工具清单 |
| 97 | mcp-registry | 连接与工具发现 | 令牌改错连接失败可读 |
| 98 | mcp-registry | 连接与工具发现 | 断开后不可再调用 |
| 99 | mcp-registry | 调用审计查询 | 审计记录五问齐备 |
| 100 | mcp-registry | 调用审计查询 | 审计按班级隔离 |
| 101 | mcp-server | 自建 MCP 工具服务器 | 带令牌握手与发现 |
| 102 | mcp-server | 自建 MCP 工具服务器 | 带令牌调用工具返回文本 |
| 103 | mcp-server | 自建 MCP 工具服务器 | 令牌错误被拒 |
| 104 | mcp-server | 自建 MCP 工具服务器 | 非法请求返回 JSON-RPC 错误 |
| 105 | mcp-server | 自建 MCP 工具服务器 | 缺失 method 的请求被拒 |
| 106 | mcp-server | 自建 MCP 工具服务器 | 工具参数非法返回 isError |
| 107 | mcp-server | 自建 MCP 工具服务器 | 非 POST 方法访问被拒 |
| 108 | mcp-server | 自建 MCP 工具服务器 | Compose 内网互通 |
| 109 | role-access | 角色区分与会话解析 | 会话解析出真实角色 |
| 110 | role-access | 学生不能上传材料 | 学生调用上传被拒绝 |
| 111 | role-access | 学生不能上传材料 | 教师调用上传被接受 |
| 112 | role-access | 角色断言在服务端强制 | 绕过前端直接调用被拒 |
| 113 | tool-calls | 技能工具引用格式与保存前校验 | 合法引用保存成功 |
| 114 | tool-calls | 技能工具引用格式与保存前校验 | 格式错误当场拒绝 |
| 115 | tool-calls | 技能工具引用格式与保存前校验 | 未连接时保存被拒 |
| 116 | tool-calls | 对话中的工具调用循环 | 命中工具的提问获得工具增强回答 |
| 117 | tool-calls | 对话中的工具调用循环 | 循环有终止也有上限 |
| 118 | tool-calls | 对话中的工具调用循环 | 工具结果进数据位不进指令位 |
| 119 | tool-calls | 对话中的工具调用循环 | 服务器未连接时运行期拒绝 |
| 120 | tool-calls | SSE meta 携带 tool_calls 且先于正文 | 调用事件先于正文 |
| 121 | tool-calls | SSE meta 携带 tool_calls 且先于正文 | 无调用时省略键 |
| 122 | user-auth | 账号密码登录 | 教师凭据有效登录成功 |
| 123 | user-auth | 账号密码登录 | 登录成功换发会话标识 |
| 124 | user-auth | 账号密码登录 | 密码错误登录失败 |
| 125 | user-auth | 账号密码登录 | 不存在的用户登录失败 |
| 126 | user-auth | 未登录访问受保护资源被引导到登录 | 未登录访问受保护 API |
| 127 | user-auth | 未登录访问受保护资源被引导到登录 | 未登录浏览器访问受保护页面 |
| 128 | user-auth | 每次请求从服务端会话解析身份 | 会话过期后访问被拒 |
| 129 | user-auth | 每次请求从服务端会话解析身份 | 篡改或伪造的 token 被拒 |
| 130 | user-auth | 每次请求从服务端会话解析身份 | 会话中的身份随用户记录实时生效 |
| 131 | user-auth | 登出立即失效 | 登出后会话立即失效 |
| 132 | user-auth | 密码必须哈希存储 | 数据库中不存明文密码 |
| 133 | user-auth | 密码必须哈希存储 | 日志不泄露明文 |

合计：133 条 Scenario。
