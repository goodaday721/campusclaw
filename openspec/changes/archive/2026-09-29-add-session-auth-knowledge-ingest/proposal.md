## Why

第 3 课课件（认证授权与知识库入库）明确了硬性要求：服务端会话认证（明确不采用 JWT）、五张表（含 sessions 与 knowledge_entries）、上传白名单仅 `.txt`/`.md` 且两表同一事务入库、本班材料可下载。已归档的 add-auth-class-isolation 实现采用 JWT、三张表、仅写 materials 且白名单含 PDF/图片，与课件要求存在多处行为分歧，须先改规约再改代码。

## What Changes

- **BREAKING** 认证由 JWT Bearer 全面切换为服务端会话：新增 `sessions` 表（user_id、expires_at），登录成功必须换发新会话标识（防会话固定），Cookie 仅持随机会话标识（HttpOnly、SameSite），登出删除会话行立即失效，每次请求从 sessions + users 表读取角色与班级。
- 数据模型扩为五张表：classes、users、sessions、materials、knowledge_entries；materials 与 knowledge_entries 均携带非空且建索引的 `class_id` 租户列。
- 上传白名单收紧为仅 `.txt`/`.md`（**BREAKING**，原 MIME 白名单含 PDF/图片）；存储名由服务端生成；落盘后 materials 与 knowledge_entries（含正文）在同一事务提交，任一步失败两表回滚并清理已写入文件，不产生孤儿文件/孤儿记录。
- 新增材料下载：教师与学生均可下载本班材料；跨班与不存在返回同构 404。
- 登录失败各原因对外响应保持一致（沿用现有行为）；班级一律取自会话，请求参数声明的一律丢弃（沿用，措辞由"令牌"改为"会话"）。
- Compose 验收补强：`down` → `up`（不带 `-v`）后数据卷中账号与材料数据仍在。
- 种子数据补两班可区分标题的示例材料（含 knowledge_entries 正文）。
- 技术栈保持 Flask + SQLite；端点路径沿用 `/auth/login`、`/materials`（本仓库规约为契约）。

## Capabilities

### New Capabilities

（无——全部复用既有能力）

### Modified Capabilities

- `user-auth`: 登录凭证由 JWT 改为服务端会话 Cookie；新增登出与会话固定防御要求；JWT 密钥要求替换为会话时效只来自服务端环境变量。
- `knowledge-materials`: 上传白名单改为 `.txt`/`.md`；上传改为 materials + knowledge_entries 两表同一事务；新增本班材料下载要求。
- `class-isolation`: 隔离依据措辞由 JWT 令牌改为服务端会话；补下载接口同构 404 要求。
- `role-access`: 角色判定措辞由令牌改为会话；明确学生上传在落盘与写库前被拒。
- `app-runtime`: 数据模型扩为五张表；补 Compose `down`→`up` 数据持久验收场景。

## Impact

- 代码：`app/routes/auth.py`、`app/middleware/auth.py`（会话改造）；`app/routes/materials.py`（白名单/下载/事务入库）；新增 `app/repositories/sessions.py`、`app/repositories/knowledge.py`、`app/services/upload.py`；`migrations/` 新增 002 迁移；`seeds/seed.py` 补材料种子；`app/config.py` 会话时效配置；`tests/` 与 `e2e_test.py` 全量适配 Cookie 会话。
- 依赖：移除 PyJWT；其余不变（Flask、bcrypt、sqlite3）。
- 部署：docker-compose.yml 无结构变化（沿用单服务 + 数据卷）；需重新构建镜像。
- 兼容：**BREAKING**——旧 JWT 客户端凭证失效，须重新登录获取会话 Cookie。
