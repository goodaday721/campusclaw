# 演示操作清单

照着顺序做，每步都写了「怎么做」和「应该看到什么」。

---

## 一、开场前先确认

```powershell
cd e:\campusclaw-mygroup
docker compose ps
```

要看到六个服务全是 Up：`web / api / db / qdrant / mcp-demo / worker`。

账号：

| 用户名 | 密码 | 角色 |
|---|---|---|
| `teacher_a` | `teacher_a_pass` | A 班教师 |
| `student_a` | `student_a_pass` | A 班学生 |
| `teacher_b` | `teacher_b_pass` | B 班教师 |
| `student_b` | `student_b_pass` | B 班学生 |

准备三个窗口：页面 `http://localhost:8080/login`、接口文档 `http://localhost:8080/swagger/index.html`、PowerShell（必须在项目目录）。

先确认额度还能不能用：

```powershell
$t = (Invoke-RestMethod -Uri http://localhost:8080/auth/login -Method Post -ContentType 'application/json' -Body '{"username":"student_a","password":"student_a_pass"}').token
curl.exe -s -o NUL -w "%{http_code}`n" -X POST http://localhost:8080/search -H "Content-Type: application/json" -H "Authorization: Bearer $t" -d "{\"query\":\"两表事务\",\"mode\":\"hybrid\"}"
```

返回 `200` 就正常演示；返回 `503` 就别点问答和助手，只演示下面不带星号的步骤（带 ★ 的需要模型额度）。

---

## 二、按顺序演示

### 1. 登录拿令牌

打开 Swagger，展开 `auth` → `POST /auth/login` → Try it out → 填：

```json
{"username": "teacher_b", "password": "teacher_b_pass"}
```

Execute，复制返回里的 `token`（不要带 `Bearer ` 三个字），点右上角 Authorize，粘进去，Authorize → Close，右上角小锁变实心。

要说明的：令牌里只有用户 id 和过期时间，**不含角色和班级**，角色班级每次请求都从数据库实时读。

---

### 2. 演示三个错误码

用 Swagger 依次点：

- 清掉 Authorize，调 `GET /api/assignments` → **401**
- 换 `student_a` 的令牌，调 `POST /api/assignments` → **403**
- 换 `student_b` 的令牌，调 `GET /materials/13` → **404**

要说明的：学生越权是 403，跨班是 404。跨班不能用 403，因为 403 等于告诉对方「这个资源存在，只是你没权限」。

---

### 3. 演示跨班下载（最有说服力的一组）

```powershell
$b = (Invoke-RestMethod -Uri http://localhost:8080/auth/login -Method Post -ContentType 'application/json' -Body '{"username":"student_b","password":"student_b_pass"}').token
curl.exe -s -o NUL -w "A班资料13 -> %{http_code}`n" -H "Authorization: Bearer $b" http://localhost:8080/materials/13/download
curl.exe -s -o NUL -w "不存在999 -> %{http_code}`n" -H "Authorization: Bearer $b" http://localhost:8080/materials/999999/download
curl.exe -s -o NUL -w "B班资料2  -> %{http_code}`n" -H "Authorization: Bearer $b" http://localhost:8080/materials/2/download
```

要看到：

```
A班资料13 -> 404
不存在999 -> 404
B班资料2  -> 200
```

要说明的：前两条返回完全一样，说明系统不泄露「这个文件其实存在」。第三条是本班文件，正常下载。

---

### 4. 上传材料

`teacher_a` 登录页面，材料区上传一个 txt 文件，列表里出现，点下载能打开。

要说明的：上传时系统做了四件事——写材料记录、切片、调 embedding 模型转成向量、写向量库。任何一步失败整体回滚，不会留下半条数据。

---

### 5. 检索（不需要模型额度）

Swagger 里 `POST /search`，用 `student_b` 的令牌：

```json
{"query": "两表事务", "mode": "keyword"}
```

要看到：命中 `materialId: 2`，是 B 班自己的材料。

再搜 A 班的内容：

```json
{"query": "一元一次方程 移项", "mode": "keyword"}
```

要看到：`hits` 是空数组。

换 `student_a` 的令牌搜同一句，要看到：命中 `materialId: 13`。

要说明的：同一个词 B 班一条都没有，A 班能搜到，因为查询条件里强制带了班级 id，学生根本拿不到别的班的切片。

顺带说明三种模式：`keyword` 用 MySQL 全文索引，不调模型；`vector` 和 `hybrid` 要调 embedding 模型，额度没了会报 503。这就是为什么刚才那条检索在额度耗尽时仍然能用。

---

### 6. 配置技能和助手

页面教师端按顺序做：

1. 填班级提示词，保存
2. 新建技能，填：

```
名称：单位换算引导
适用条件：单位换算
工具：unit_convert@campus-tools
资料：数学
启用：是

遇到单位换算时先调用工具完成换算，再引导学生理解进率。
```

3. 新建助手，把上面这个技能勾上，启用

要说明的：技能是班级里的独立资源，可以同时被多个助手绑定；助手还能限定只检索哪几份材料。技能停用后，绑它的所有助手立刻不再注入这段引导，不用重启。

---

### 7. ★ 提问（需要额度）

`student_a` 登录，新建会话，发一条和资料相关的问题。

要看到：文字一个个出现（流式），回答上方有引用出处。

要说明的：回答前先检索本班资料，拿到片段再让模型作答；如果一条资料都没检索到，就直接回「资料中未找到相关内容」，不调模型，避免编造。

---

### 8. MCP 工具

先在页面「MCP 工具服务」里给 `campus-tools` 点连接，要看到状态变成已连接、发现 2 个工具。

然后用学生账号提问：**10千克等于多少克**

要看到：回答上方出现 `unit_convert@campus-tools / ok / 1 轮`，正文给出换算结果。

再补一个对照：技能里不写 `工具：` 那行，同样的问题会回「资料中未找到相关内容」。

查调用记录：

```powershell
docker compose exec -T db sh -c 'mysql -uroot -p$MYSQL_ROOT_PASSWORD campusclaw -e "SELECT id,user_id,tool_name,status,round_no,created_at FROM mcp_call_logs ORDER BY id DESC LIMIT 5"'
```

要看到：`unit_convert | ok | 1` 这样的行。

要说明的四点：

- 模型只负责说「我要调 unit_convert，参数是这些」，真正发请求的是我们的服务端
- 参数会先按工具的声明校验一遍，不合格就不发出去
- 工具返回的内容只当数据用，不当指令用，防止对方服务器在返回值里塞指令劫持对话
- 每问最多 3 轮提议、5 次执行，超了就用已有数据作答

---

### 9. 作业和批改

```
POST /api/assignments                  教师建作业
POST /api/assignments/1/submissions    学生提交 → 202
GET  /api/submissions/9                查状态 → pending / running / succeeded
docker compose logs --tail=20 worker   看 worker 日志
```

要说明的四点：提交和任务在同一个事务里写；同一个提交重复提交只会批改一次；多个 worker 抢任务不会抢到同一条；worker 崩了重启会把卡住超过 60 秒的任务重新排队。

---

### 10. 安全检查

```powershell
docker compose exec -T api python scripts/check_security.py
```

要看到：SEC-05 通过（没有密钥泄漏），SEC-06 是红的（没装 pip-audit，出不了漏洞基线）。

再打开 `reports` 目录，指出六个文件：`security-precheck.md`、`risk-authz.md`、`risk-concurrency.md`、`risk-transaction.md`、`security-baseline.md`、`review-01.md`。

要说明的：两条红是故意留的，这门课的规则是只记录现象、不提前修，下一课再修复并给修复前后对照。

---

### 11. 接口文档怎么介绍

别说一个个接口，只说结构：一共 27 个路径、37 个操作，分成 8 组——认证、材料、检索问答、助手配置、会话、MCP、作业、系统。四个动词意思全站统一：GET 读、POST 建或触发、PUT 整体替换、DELETE 删。错误统一返回 `{"error": "..."}`。

要说明的用途：一是说明书，别人对接不用问；二是不写代码就能试，刚才那几个 401/403/404 就是这么点的；三是接口清单，少一个就说明文档没写完。

---

### 12. 最后跑一次测试

```powershell
docker compose exec -T api python -m pytest -q
```

要看到全部通过。说明：这套测试用离线的假模型网关，不消耗额度；另外两条打真实网关的 e2e 和 apitest 在有额度时才会跑。

---

## 三、被问到怎么答

| 问题 | 回答 |
|---|---|
| 跨班为什么返回 404 而不是 403 | 403 等于承认资源存在，404 和「不存在」表现一致，不泄露信息 |
| 没检索到为什么不直接让模型回答 | 没有依据就容易编造，所以固定回一句「资料中未找到相关内容」 |
| 工具是谁执行的 | 我们的服务端执行。模型只是提议调哪个工具、传什么参数，它连对方的地址和令牌都没有 |
| 工具返回值会不会有风险 | 只当数据拼进消息，不当指令用；发现里面带「忽略前面的指令」这类句子整条丢弃 |
| 为什么要限制工具调用次数 | 防止模型反复调用停不下来，也控制成本 |
| 回答到一半断了会怎样 | 消息在回答完成时才写入数据库，中途断了不会留下半截记录 |
| 批改会不会重复打分 | 同一份提交有幂等标识，结果只写一次，重试不会覆盖 |
| 密钥放在哪 | 只在本地 `.env`，不进代码、不进日志、不进接口响应 |
| 为什么只有 8080 端口对外开放 | 其他服务都在内网，外面连不上，减少暴露面 |
| 检索和回答分别用的什么模型 | 检索用向量模型把文字变成数字，回答用对话模型；关键词检索两个都不用 |

---

## 四、出问题怎么办

| 现象 | 处理 |
|---|---|
| 问答或助手报 503 | 网关当天额度用完了，属于外部服务降级，改演示关键词检索和下面的脚本 |
| Swagger 报 401 | 令牌过期，重新登录换一个 |
| 命令行报 `no configuration file provided` | 没在项目目录，先 `cd e:\campusclaw-mygroup` |
| 页面点下载没反应 | 从页面按钮点，不要直接复制地址到浏览器打开（浏览器不会带令牌） |
| 数据库那条命令报引号错误 | 外层用单引号，别用双引号 |
| worker 日志没新内容 | 正常，它在空转等任务，提交一份作业再看 |
| 现场报错 | 别当场改代码，切到提前存好的截图 |
