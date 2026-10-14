"""GET /openapi.json + GET /swagger/index.html — API documentation (lesson 5).

The OpenAPI document is a hand-written dict covering every public endpoint
(legacy lesson-1..4 routes plus the lesson-5 /api/ assistant routes) with
request/response shapes, error codes and Bearer auth markers. The Swagger UI
page references the CDN-hosted swagger-ui-dist and loads /openapi.json, so
browsers can read the docs and try calls (Authorize button takes the JWT).
"""
from flask import Blueprint, jsonify

docs_bp = Blueprint("api_docs", __name__)


def _err(description: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        },
    }


def _json(schema: dict, description: str = "OK") -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}

_JSON_BODY = {
    "required": True,
    "content": {"application/json": {"schema": {}}},
}


def _protected(responses: dict) -> dict:
    out = {"401": _err("未登录或 token 无效/已登出")}
    out.update(responses)
    return out


def _path_id(description: str) -> dict:
    return {
        "name": "id",
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
        "description": description,
    }


_OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "CampusClaw API",
        "version": "5.0.0",
        "description": (
            "班级课程资料问答与解题助手。第 1-4 课的登录/材料/检索/问答端点 "
            "与第 5 课的提示词/技能/智能体/流式会话端点（/api/ 前缀）。"
            "除公开端点外均需 Authorization: Bearer <JWT>。"
        ),
    },
    "servers": [{"url": "/"}],
    "tags": [
        {"name": "auth", "description": "登录认证"},
        {"name": "materials", "description": "材料上传与管理"},
        {"name": "retrieval", "description": "检索与问答"},
        {"name": "assistant", "description": "第 5 课解题助手（提示词/技能/智能体/会话）"},
        {"name": "system", "description": "系统"},
    ],
    "paths": {
        "/health": {
            "get": {
                "tags": ["system"],
                "summary": "存活探针（不含 DB 探活）",
                "responses": {"200": _json({"type": "object"})},
            }
        },
        "/auth/login": {
            "post": {
                "tags": ["auth"],
                "summary": "登录，返回 JWT 与用户信息",
                "requestBody": {
                    **_JSON_BODY,
                    "content": {
                        "application/json": {
                            "schema": _ref("LoginRequest"),
                        }
                    },
                },
                "responses": {
                    "200": _json(_ref("LoginResponse"), "登录成功"),
                    "400": _err("请求体不合法"),
                    "401": _err("用户名或密码错误（两种失败响应一致）"),
                },
            }
        },
        "/auth/logout": {
            "post": {
                "tags": ["auth"],
                "summary": "登出（撤销服务端会话，token 立即失效）",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json({"type": "object"}),
                    "401": _err("未登录"),
                },
            }
        },
        "/auth/me": {
            "get": {
                "tags": ["auth"],
                "summary": "当前登录用户（实时读取 users 表身份）",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json(_ref("User")),
                    "401": _err("未登录"),
                },
            }
        },
        "/materials": {
            "get": {
                "tags": ["materials"],
                "summary": "本班材料列表",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json({"type": "object"}),
                    "401": _err("未登录"),
                },
            },
            "post": {
                "tags": ["materials"],
                "summary": "上传材料（仅教师，multipart/form-data：file）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {"file": {"type": "string", "format": "binary"}},
                                "required": ["file"],
                            }
                        }
                    },
                },
                "responses": {
                    "201": _json({"type": "object"}, "上传成功"),
                    "400": _err("未提供文件/文件名为空/超过大小限制"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可上传"),
                },
            },
        },
        "/materials/{id}": {
            "get": {
                "tags": ["materials"],
                "summary": "材料详情（本班）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("材料 id")],
                "responses": {
                    "200": _json({"type": "object"}),
                    "401": _err("未登录"),
                    "404": _err("不存在或不属于本班"),
                },
            }
        },
        "/materials/{id}/download": {
            "get": {
                "tags": ["materials"],
                "summary": "下载材料文件",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("材料 id")],
                "responses": {
                    "200": {"description": "文件内容"},
                    "401": _err("未登录"),
                    "404": _err("不存在或不属于本班"),
                },
            }
        },
        "/materials/{id}/reindex": {
            "post": {
                "tags": ["materials"],
                "summary": "重建材料的切片与向量索引（仅教师）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("材料 id")],
                "responses": {
                    "200": _json({"type": "object"}, "重建结果摘要"),
                    "400": _err("参数错误"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可重建"),
                    "404": _err("不存在或不属于本班"),
                },
            }
        },
        "/search": {
            "post": {
                "tags": ["retrieval"],
                "summary": "本班知识库检索（keyword/vector/hybrid）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {
                        "application/json": {"schema": _ref("SearchRequest")}
                    },
                },
                "responses": {
                    "200": _json(_ref("SearchResponse")),
                    "400": _err("query 为空或 mode 非法"),
                    "401": _err("未登录"),
                    "503": _err("向量检索依赖不可用"),
                },
            }
        },
        "/ask": {
            "post": {
                "tags": ["retrieval"],
                "summary": "有依据问答（一次性返回整段答案与引用）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("AskRequest")}},
                },
                "responses": {
                    "200": _json(_ref("AskResponse")),
                    "400": _err("question 为空"),
                    "401": _err("未登录"),
                    "503": _err("检索或对话网关不可用"),
                },
            }
        },
        "/api/prompt": {
            "get": {
                "tags": ["assistant"],
                "summary": "读取本班系统提示词",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json(_ref("PromptResponse")),
                    "401": _err("未登录"),
                },
            },
            "put": {
                "tags": ["assistant"],
                "summary": "更新本班系统提示词（仅教师；下一轮回答生效）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {
                        "application/json": {"schema": _ref("PromptPutRequest")}
                    },
                },
                "responses": {
                    "200": _json(_ref("PromptResponse")),
                    "400": _err("body 为空"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可修改"),
                },
            },
        },
        "/api/skills": {
            "get": {
                "tags": ["assistant"],
                "summary": "技能列表（学生仅见启用中的）",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json(_ref("SkillListResponse")),
                    "401": _err("未登录"),
                },
            },
            "post": {
                "tags": ["assistant"],
                "summary": "创建技能（仅教师；body 为单段 source 文本）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("SkillSourceRequest")}},
                },
                "responses": {
                    "201": _json(_ref("SkillResponse"), "创建成功"),
                    "400": _err("source 为空或解析失败（缺 名称/正文）"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可创建"),
                },
            },
        },
        "/api/skills/{id}": {
            "put": {
                "tags": ["assistant"],
                "summary": "更新技能（仅教师；body 为单段 source 文本）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("技能 id")],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("SkillSourceRequest")}},
                },
                "responses": {
                    "200": _json(_ref("SkillResponse")),
                    "400": _err("source 为空或解析失败"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可修改"),
                    "404": _err("技能不存在或不属于本班"),
                },
            },
            "delete": {
                "tags": ["assistant"],
                "summary": "删除技能（仅教师；同时解除智能体绑定）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("技能 id")],
                "responses": {
                    "204": {"description": "删除成功"},
                    "401": _err("未登录"),
                    "403": _err("仅教师可删除"),
                    "404": _err("技能不存在或不属于本班"),
                },
            },
        },
        "/api/agents": {
            "get": {
                "tags": ["assistant"],
                "summary": "智能体列表（学生仅见启用中的）",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json(_ref("AgentListResponse")),
                    "401": _err("未登录"),
                },
            },
            "post": {
                "tags": ["assistant"],
                "summary": "创建智能体（仅教师）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("AgentRequest")}},
                },
                "responses": {
                    "201": _json(_ref("AgentResponse"), "创建成功"),
                    "400": _err("name 为空或字段类型不合法"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可创建"),
                    "404": _err("绑定的技能/材料不属于本班"),
                },
            },
        },
        "/api/agents/{id}": {
            "get": {
                "tags": ["assistant"],
                "summary": "智能体详情（学生访问停用的智能体返回 404）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("智能体 id")],
                "responses": {
                    "200": _json(_ref("AgentResponse")),
                    "401": _err("未登录"),
                    "404": _err("不存在/不属于本班/（学生）已停用"),
                },
            },
            "put": {
                "tags": ["assistant"],
                "summary": "更新智能体（仅教师；全量替换）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("智能体 id")],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("AgentRequest")}},
                },
                "responses": {
                    "200": _json(_ref("AgentResponse")),
                    "400": _err("name 为空或字段类型不合法"),
                    "401": _err("未登录"),
                    "403": _err("仅教师可修改"),
                    "404": _err("不存在/不属于本班/绑定资源跨班"),
                },
            },
        },
        "/api/conversations": {
            "get": {
                "tags": ["assistant"],
                "summary": "本人的会话列表（按更新时间倒序）",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": _json(_ref("ConversationListResponse")),
                    "401": _err("未登录"),
                },
            },
            "post": {
                "tags": ["assistant"],
                "summary": "新建会话（body: agent_id；智能体须本班且对学生启用）",
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {
                        "application/json": {"schema": _ref("ConversationCreateRequest")}
                    },
                },
                "responses": {
                    "201": _json(_ref("ConversationResponse"), "创建成功"),
                    "400": _err("agent_id 缺失或类型错误"),
                    "401": _err("未登录"),
                    "404": _err("智能体不存在/跨班/（学生）已停用"),
                },
            },
        },
        "/api/conversations/{id}": {
            "get": {
                "tags": ["assistant"],
                "summary": "会话详情与全部消息（仅本人，跨班 404）",
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("会话 id")],
                "responses": {
                    "200": _json(_ref("ConversationDetailResponse")),
                    "401": _err("未登录"),
                    "404": _err("不属于当前用户或跨班"),
                },
            }
        },
        "/api/conversations/{id}/messages": {
            "post": {
                "tags": ["assistant"],
                "summary": (
                    "发送消息并流式获取回答（SSE：meta→delta*→done；"
                    "流开始前的错误返回普通 JSON）"
                ),
                "security": [{"bearerAuth": []}],
                "parameters": [_path_id("会话 id")],
                "requestBody": {
                    **_JSON_BODY,
                    "content": {"application/json": {"schema": _ref("MessageRequest")}},
                },
                "responses": {
                    "200": {
                        "description": (
                            "text/event-stream：event meta（citations）→ "
                            "多个 event delta（增量文本）→ event done（message_id）"
                        ),
                        "content": {"text/event-stream": {"schema": {"type": "string"}}},
                    },
                    "400": _err("content 为空"),
                    "401": _err("未登录"),
                    "404": _err("会话/智能体不存在、跨班或（学生）已停用"),
                    "503": _err("检索或对话网关不可用"),
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "登录接口返回的三段式 JWT",
            }
        },
        "schemas": {
            "Error": {
                "type": "object",
                "properties": {"error": {"type": "string", "example": "not found"}},
                "required": ["error"],
            },
            "LoginRequest": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                },
                "required": ["username", "password"],
            },
            "LoginResponse": {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "description": "三段式 JWT"},
                    "user": _ref("User"),
                },
                "required": ["token", "user"],
            },
            "User": {
                "type": "object",
                "properties": {
                    "userId": {"type": "integer"},
                    "username": {"type": "string"},
                    "role": {"type": "string", "enum": ["teacher", "student"]},
                    "classId": {"type": "integer"},
                },
            },
            "SearchRequest": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["keyword", "vector", "hybrid"],
                        "default": "hybrid",
                    },
                },
                "required": ["query"],
            },
            "SearchResponse": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string"},
                    "results": {
                        "type": "array",
                        "items": _ref("SearchHit"),
                    },
                },
            },
            "SearchHit": {
                "type": "object",
                "properties": {
                    "chunkId": {"type": "integer"},
                    "materialId": {"type": "integer"},
                    "materialTitle": {"type": "string"},
                    "chunkIndex": {"type": "integer"},
                    "excerpt": {"type": "string"},
                    "materialUrl": {"type": "string"},
                },
            },
            "AskRequest": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "history": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "可选的既往对话轮次（服务端会清洗）",
                    },
                },
                "required": ["question"],
            },
            "AskResponse": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "citations": {"type": "array", "items": _ref("Citation")},
                },
            },
            "Citation": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer"},
                    "materialId": {"type": "integer"},
                    "materialTitle": {"type": "string"},
                    "chunkIndex": {"type": "integer"},
                    "materialUrl": {"type": "string"},
                },
            },
            "PromptResponse": {
                "type": "object",
                "properties": {
                    "classId": {"type": "integer"},
                    "body": {"type": "string"},
                },
            },
            "PromptPutRequest": {
                "type": "object",
                "properties": {"body": {"type": "string"}},
                "required": ["body"],
            },
            "SkillSourceRequest": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "单段文本：名称：/适用条件：/工具：/资料：/启用： 行字段，"
                            "空行后为引导指令正文"
                        ),
                    }
                },
                "required": ["source"],
            },
            "Skill": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "classId": {"type": "integer"},
                    "name": {"type": "string"},
                    "trigger": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                    "source": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
            },
            "SkillResponse": {
                "type": "object",
                "properties": {"skill": _ref("Skill")},
            },
            "SkillListResponse": {
                "type": "object",
                "properties": {
                    "skills": {"type": "array", "items": _ref("Skill")}
                },
            },
            "AgentRequest": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "prompt": {"type": "string", "nullable": True},
                    "skill_ids": {"type": "array", "items": {"type": "integer"}},
                    "material_ids": {"type": "array", "items": {"type": "integer"}},
                    "enabled": {"type": "boolean", "default": True},
                },
                "required": ["name"],
            },
            "Agent": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "classId": {"type": "integer"},
                    "name": {"type": "string"},
                    "prompt": {"type": "string", "nullable": True},
                    "skillIds": {"type": "array", "items": {"type": "integer"}},
                    "materialIds": {"type": "array", "items": {"type": "integer"}},
                    "enabled": {"type": "boolean"},
                },
            },
            "AgentResponse": {
                "type": "object",
                "properties": {"agent": _ref("Agent")},
            },
            "AgentListResponse": {
                "type": "object",
                "properties": {
                    "agents": {"type": "array", "items": _ref("Agent")}
                },
            },
            "ConversationCreateRequest": {
                "type": "object",
                "properties": {"agent_id": {"type": "integer"}},
                "required": ["agent_id"],
            },
            "Conversation": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "agentId": {"type": "integer"},
                    "agentName": {"type": "string"},
                    "title": {"type": "string"},
                    "createdAt": {"type": "string", "format": "date-time"},
                    "updatedAt": {"type": "string", "format": "date-time"},
                },
            },
            "ConversationResponse": {
                "type": "object",
                "properties": {"conversation": _ref("Conversation")},
            },
            "ConversationListResponse": {
                "type": "object",
                "properties": {
                    "conversations": {"type": "array", "items": _ref("Conversation")}
                },
            },
            "ConversationDetailResponse": {
                "type": "object",
                "properties": {
                    "conversation": _ref("Conversation"),
                    "messages": {"type": "array", "items": _ref("Message")},
                },
            },
            "Message": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "role": {"type": "string", "enum": ["user", "assistant"]},
                    "content": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "nullable": True,
                        "items": _ref("Citation"),
                    },
                    "skillName": {"type": "string", "nullable": True},
                    "createdAt": {"type": "string", "format": "date-time"},
                },
            },
            "MessageRequest": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
    "security": [],
}


@docs_bp.route("/openapi.json", methods=["GET"])
def openapi_json():
    return jsonify(_OPENAPI), 200


_SWAGGER_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>CampusClaw API - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: "/openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
        persistAuthorization: true,
      });
    };
  </script>
</body>
</html>
"""


@docs_bp.route("/swagger/index.html", methods=["GET"])
def swagger_ui():
    return _SWAGGER_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}

