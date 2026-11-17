# Tasks

- [x] 1. 技能上传
  - [x] 1.1 `app/routes/api_skills.py` 新增 `POST /api/skills/import`
  - [x] 1.2 `.md` / `.json` 双格式解析 + 规整 source
  - [x] 1.3 415/413/400/409/403/401 错误路径
  - [x] 1.4 复用工具引用四查
  - [x] 1.5 审计 `create/skill`，detail 含 import 与文件名
  - [x] 1.6 教师仪表盘技能区新增文件选择 + 导入按钮

- [x] 2. 关怀式对话
  - [x] 2.1 `seeds/seed.py` 新增 `SEED_CARE_SKILL` 并复用 `_seed_extra_skill`
  - [x] 2.2 `app/services/chat.py` 新增 `needs_care` / `CARE_PATTERNS` / `CARE_SKILL_NAME`
  - [x] 2.3 `_prepare` 条件注入 + 返回 `care` 标记
  - [x] 2.4 两处零命中短路由关怀豁免

- [x] 3. 文档与接口描述
  - [x] 3.1 `app/routes/api_docs.py` 新增 `/api/skills/import`
  - [x] 3.2 `README.md` 拓展章节
  - [x] 3.3 `docs/standards/ai.md` 内置技能清单补关怀式对话

- [x] 4. 测试
  - [x] 4.1 `tests/test_skill_import.py`（16 例）
  - [x] 4.2 `tests/test_care_skill.py`（7 例）
  - [x] 4.3 全量 pytest 通过（104 + 105 = 209）

- [x] 5. 验收
  - [x] 5.1 `openspec validate --all --strict --no-interactive` 0 failed
  - [x] 5.2 归档
