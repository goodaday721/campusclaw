"""前端页面：登录、Dashboard（材料列表/上传/下载/检索/问答/退出）。"""
from flask import Blueprint, redirect, render_template_string

pages_bp = Blueprint("pages", __name__)

STYLE = """
<style>
  /* 北大红主题：主色 #94070A（北大校色红），金色仅作小面积点缀 */
  * { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --pku-red: #94070a;
    --pku-red-dark: #78050a;
    --pku-red-light: #b8302f;
    --pku-gold: #c5a572;
  }
  body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f3f1; color: #2b2b2b; }

  .navbar { background: var(--pku-red); padding: 14px 28px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 10px rgba(148,7,10,.25); }
  .navbar .brand { color: #fff; font-size: 18px; font-weight: bold; letter-spacing: 1px; }
  .navbar .user-info { color: #f3e9e9; font-size: 14px; display: flex; align-items: center; }
  .navbar .user-info span.role { background: var(--pku-gold); color: #4a2c00; padding: 2px 10px; border-radius: 10px; font-size: 12px; margin-left: 8px; font-weight: 600; }
  .navbar .logout-btn { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,.55); padding: 6px 18px; border-radius: 4px; cursor: pointer; margin-left: 16px; font-size: 13px; transition: all .2s; }
  .navbar .logout-btn:hover { background: #fff; color: var(--pku-red); border-color: #fff; }

  .container { max-width: 900px; margin: 28px auto; padding: 0 16px; }
  .card { background: #fff; border-radius: 10px; box-shadow: 0 2px 12px rgba(148,7,10,.08); margin-bottom: 18px; overflow: hidden; border: 1px solid #f0e6e4; }
  .card-header { background: var(--pku-red); color: #fff; padding: 13px 22px; font-size: 16px; font-weight: bold; letter-spacing: .5px; }
  .card-body { padding: 22px; }

  .material-item { display: flex; justify-content: space-between; align-items: center; padding: 13px 0; border-bottom: 1px solid #f0e6e4; }
  .material-item:last-child { border-bottom: none; }
  .material-item .name { font-size: 15px; font-weight: 500; }
  .material-item .meta { font-size: 12px; color: #999; margin-top: 4px; }
  .download-btn { background: #fff; color: var(--pku-red); text-decoration: none; padding: 6px 18px; border-radius: 4px; font-size: 13px; border: 1px solid var(--pku-red); transition: all .2s; }
  .download-btn:hover { background: var(--pku-red); color: #fff; }

  .upload-form { margin-top: 18px; }
  .upload-form input[type="file"] { margin-right: 8px; font-size: 13px; }
  .upload-form button { background: var(--pku-red); color: #fff; border: none; padding: 8px 28px; border-radius: 4px; cursor: pointer; transition: background .2s; }
  .upload-form button:hover { background: var(--pku-red-dark); }
  .upload-form button:disabled { background: #b9a8a6; cursor: not-allowed; }

  .err-msg { color: var(--pku-red-light); font-size: 14px; margin-top: 8px; }
  .success-msg { color: #1e8e4a; font-size: 14px; margin-top: 8px; }
  .empty { text-align: center; color: #aa9999; padding: 40px 0; }

  .ask-row, .search-row { display: flex; gap: 8px; }
  .ask-row input, .search-row input { flex: 1; padding: 10px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; transition: border-color .2s, box-shadow .2s; }
  .search-row select { padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; background: #fff; }
  .ask-row input:focus, .search-row input:focus, .search-row select:focus, .login-box input:focus { outline: none; border-color: var(--pku-red); box-shadow: 0 0 0 3px rgba(148,7,10,.12); }
  .ask-row button, .search-row button { background: var(--pku-red); color: #fff; border: none; padding: 8px 22px; border-radius: 4px; cursor: pointer; white-space: nowrap; transition: background .2s; }
  .ask-row button:hover, .search-row button:hover { background: var(--pku-red-dark); }
  .ask-row button:disabled, .search-row button:disabled { background: #b9a8a6; cursor: not-allowed; }

  .hit-item { padding: 14px; border: 1px solid #f0e6e4; border-left: 3px solid var(--pku-red); border-radius: 6px; margin-bottom: 10px; background: #fdfbfa; }
  .hit-item .hit-title { font-weight: 600; font-size: 14px; }
  .hit-item .hit-meta { font-size: 12px; color: #999; margin: 4px 0; }
  .hit-item .hit-excerpt { font-size: 13px; color: #555; line-height: 1.7; }
  .hit-item a { font-size: 12px; color: var(--pku-red); text-decoration: none; font-weight: 500; }
  .hit-item a:hover { text-decoration: underline; }

  #answerText { background: #fdf6f5; border-left: 4px solid var(--pku-red); padding: 14px; border-radius: 4px; font-size: 14px; line-height: 1.8; margin-top: 12px; white-space: pre-wrap; }
  .cite-list { margin-top: 10px; font-size: 12px; color: #666; }
  .cite-list a { color: var(--pku-red); margin-right: 12px; text-decoration: none; }
  .cite-list a:hover { text-decoration: underline; }

  /* 第5课：解题助手（会话流式对话）+ 教师智能体配置 */
  .assistant-grid { display: grid; grid-template-columns: 230px 1fr; gap: 14px; }
  @media (max-width: 720px) { .assistant-grid { grid-template-columns: 1fr; } }
  .conv-list { display: flex; flex-direction: column; gap: 6px; max-height: 330px; overflow-y: auto; }
  .conv-item { padding: 9px 11px; border: 1px solid #f0e6e4; border-radius: 6px; font-size: 13px; cursor: pointer; background: #fff; transition: all .15s; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-item:hover { border-color: var(--pku-red-light); }
  .conv-item.active { background: var(--pku-red); color: #fff; border-color: var(--pku-red); }
  .conv-item .conv-agent { display: block; font-size: 11px; opacity: .75; margin-top: 2px; }
  .chat-box { height: 330px; overflow-y: auto; background: #fdfbfa; border: 1px solid #f0e6e4; border-radius: 6px; padding: 14px; }
  .msg { display: flex; margin-bottom: 12px; }
  .msg.user { justify-content: flex-end; }
  .bubble { max-width: 82%; padding: 10px 14px; border-radius: 10px; font-size: 14px; line-height: 1.75; white-space: pre-wrap; word-break: break-word; }
  .msg.user .bubble { background: var(--pku-red); color: #fff; border-bottom-right-radius: 3px; }
  .msg.assistant .bubble { background: #fff; border: 1px solid #f0e6e4; border-bottom-left-radius: 3px; }
  .msg .cites { margin-top: 8px; font-size: 12px; }
  .msg .cites a { color: var(--pku-red); margin-right: 10px; text-decoration: none; }
  .msg .cites a:hover { text-decoration: underline; }
  .msg .skill-tag { display: inline-block; font-size: 11px; color: #8a5a2a; background: #f7ece4; border-radius: 8px; padding: 1px 8px; margin-bottom: 6px; }
  .tool-calls { margin-bottom: 6px; display: flex; flex-direction: column; gap: 4px; }
  .tool-call { display: flex; align-items: center; gap: 8px; font-size: 12px; background: #f5f9f5; border: 1px solid #dbeadb; border-radius: 6px; padding: 5px 9px; flex-wrap: wrap; }
  .tool-call.denied { background: #faf3f2; border-color: #ead4d2; }
  .tool-call.error { background: #fdf6ec; border-color: #f0e0c8; }
  .tool-call .tool-ref { font-weight: 700; color: #2d5a2d; }
  .tool-call.denied .tool-ref, .tool-call.error .tool-ref { color: #8a2a2a; }
  .tool-call .tool-status { font-size: 11px; color: #556; }
  .tool-call .tool-text { color: #667; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .cfg-row { margin-bottom: 14px; }
  .cfg-row > label { display: block; font-size: 13px; color: #555; margin-bottom: 4px; font-weight: 600; }
  .cfg-row textarea, .cfg-row input[type=text], .cfg-row select { width: 100%; padding: 9px 11px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; font-family: inherit; }
  .cfg-row textarea:focus, .cfg-row input[type=text]:focus { outline: none; border-color: var(--pku-red); box-shadow: 0 0 0 3px rgba(148,7,10,.12); }
  .btn { background: var(--pku-red); color: #fff; border: none; padding: 7px 18px; border-radius: 4px; cursor: pointer; font-size: 13px; transition: background .2s; }
  .btn:hover { background: var(--pku-red-dark); }
  .btn.secondary { background: #fff; color: var(--pku-red); border: 1px solid var(--pku-red); }
  .btn.secondary:hover { background: #fdf6f5; }
  .btn.small { padding: 4px 12px; font-size: 12px; }
  .skill-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px dashed #f0e6e4; font-size: 13px; }
  .skill-item:last-child { border-bottom: none; }
  .skill-item .ops { display: flex; gap: 6px; }
  .tag { display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 8px; background: #fbecec; color: var(--pku-red-light); margin-left: 6px; }
  .tag.on { background: #e8f5ee; color: #1e8e4a; }
  .checks { display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px; padding: 6px 0; }
  .checks label { display: flex; align-items: center; gap: 4px; font-weight: normal; }

  .login-box { max-width: 400px; margin: 80px auto; background: #fff; border-radius: 10px; box-shadow: 0 8px 28px rgba(148,7,10,.15); padding: 44px 40px; border-top: 4px solid var(--pku-red); }
  .login-box h2 { text-align: center; margin-bottom: 28px; color: var(--pku-red); letter-spacing: 1px; }
  .login-box label { display: block; margin-bottom: 6px; font-size: 14px; color: #555; }
  .login-box input { width: 100%; padding: 11px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 16px; transition: border-color .2s, box-shadow .2s; }
  .login-box button { width: 100%; padding: 12px; background: var(--pku-red); color: #fff; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; transition: background .2s; letter-spacing: 4px; }
  .login-box button:hover { background: var(--pku-red-dark); }
  .login-box .err { color: var(--pku-red-light); text-align: center; margin-top: 12px; }
</style>
"""

LOGIN_PAGE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>登录 - CampusClaw</title>__STYLE__</head>
<body>
<div class="login-box">
  <h2>🎓 CampusClaw 登录</h2>
  <form id="loginForm">
    <label>用户名</label>
    <input name="username" type="text" placeholder="请输入用户名" required>
    <label>密码</label>
    <input name="password" type="password" placeholder="请输入密码" required>
    <button type="submit">登录</button>
    <div class="err" id="err"></div>
  </form>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const next = new URLSearchParams(location.search).get('next') || '/dashboard';
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: f.username.value, password: f.password.value})
  });
  if (res.ok) {
    const data = await res.json();
    localStorage.setItem('cc_token', data.token);
    window.location.href = next;
  } else {
    document.getElementById('err').textContent = '用户名或密码错误';
  }
});
</script>
</body></html>
"""

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Dashboard - CampusClaw</title>__STYLE__</head>
<body>
<div class="navbar">
  <span class="brand">🎓 CampusClaw 知识库</span>
  <div class="user-info">
    <span id="username"></span>
    <span class="role" id="role"></span>
    <button class="logout-btn" onclick="logout()">退出登录</button>
  </div>
</div>

<div class="container">
  <div class="card">
    <div class="card-header">📚 班级材料</div>
    <div class="card-body">
      <div id="materialList"><div class="empty">加载中...</div></div>
      <div class="upload-form" id="uploadArea" style="display:none">
        <h3 style="margin-bottom:8px">上传新材料</h3>
        <form id="uploadForm" style="display:flex; align-items:center;">
          <input type="file" name="file" accept=".txt,.md" required>
          <button type="submit">上传</button>
        </form>
        <div class="err-msg" id="uploadErr"></div>
        <div class="success-msg" id="uploadOk"></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">🔎 知识库检索（限本班）</div>
    <div class="card-body">
      <div class="search-row">
        <input type="text" id="searchQuery" placeholder="输入自然语言问题或关键词，仅检索本班材料">
        <select id="searchMode">
          <option value="hybrid">混合检索</option>
          <option value="keyword">关键字</option>
          <option value="vector">向量</option>
        </select>
        <button type="button" onclick="doSearch()">检索</button>
      </div>
      <div class="err-msg" id="searchErr"></div>
      <div id="searchResults" style="margin-top:12px"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">💬 知识库问答（有依据才回答）</div>
    <div class="card-body">
      <div class="ask-row">
        <input type="text" id="askQuestion" placeholder="就本班材料提问；资料中没有依据时会直接告知未找到">
        <button type="button" onclick="doAsk()">提问</button>
      </div>
      <div class="err-msg" id="askErr"></div>
      <div id="answerText" style="display:none"></div>
      <div class="cite-list" id="citeList"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">🤖 解题助手（流式对话）</div>
    <div class="card-body">
      <div class="cfg-row" style="max-width:340px">
        <label>选择智能体</label>
        <select id="agentSelect" onchange="onAgentChange()"></select>
      </div>
      <div class="assistant-grid">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <strong style="font-size:13px">我的会话</strong>
            <button class="btn small" type="button" onclick="newConversation()">+ 新会话</button>
          </div>
          <div id="convList" class="conv-list"><div class="empty">加载中...</div></div>
        </div>
        <div>
          <div class="chat-box" id="chatBox"><div class="empty">选择或新建会话后开始提问</div></div>
          <div class="ask-row" style="margin-top:10px">
            <input type="text" id="chatInput" placeholder="向解题助手提问（回答前会检索本班资料并给出出处）" disabled>
            <button type="button" id="chatSendBtn" onclick="sendChatMessage()" disabled>发送</button>
          </div>
          <div class="err-msg" id="chatErr"></div>
        </div>
      </div>
    </div>
  </div>

  <div class="card" id="configCard" style="display:none">
    <div class="card-header">🛠 智能体配置（仅教师）</div>
    <div class="card-body">
      <div class="cfg-row">
        <label>班级系统提示词（保存后从下一轮回答生效）</label>
        <textarea id="promptBody" rows="3"></textarea>
        <div style="margin-top:6px">
          <button class="btn" type="button" onclick="savePrompt()">保存提示词</button>
          <span class="success-msg" id="promptOk"></span>
          <span class="err-msg" id="promptErr" style="margin:0"></span>
        </div>
      </div>
      <hr style="border:none;border-top:1px solid #f0e6e4;margin:16px 0">
      <div class="cfg-row">
        <label>解题引导技能</label>
        <div id="skillList"></div>
      </div>
      <div class="cfg-row">
        <label>技能 source 文本（新建或编辑后提交；首个空行后为引导指令正文）</label>
        <textarea id="skillSource" rows="9" placeholder="名称：方程解题引导&#10;适用条件：一元一次方程&#10;工具：knowledge_search&#10;资料：数学&#10;启用：是&#10;&#10;（空行后写引导指令正文，回答时整段注入）"></textarea>
        <div style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <button class="btn" type="button" onclick="submitSkill(false)">新建技能</button>
          <button class="btn secondary" type="button" id="skillUpdateBtn" onclick="submitSkill(true)" style="display:none">更新该技能</button>
          <button class="btn secondary" type="button" id="skillCancelBtn" onclick="resetSkillEditor()" style="display:none">取消编辑</button>
          <span class="err-msg" id="skillErr" style="margin:0"></span>
          <span class="success-msg" id="skillOk"></span>
        </div>
      </div>
      <hr style="border:none;border-top:1px solid #f0e6e4;margin:16px 0">
      <div class="cfg-row">
        <label>智能体</label>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;max-width:420px">
          <select id="agentEditSelect" onchange="loadAgentEditor()"></select>
          <button class="btn secondary small" type="button" onclick="resetAgentEditor()">新建</button>
        </div>
        <label>名称</label>
        <input type="text" id="agentName" style="margin-bottom:10px">
        <label>提示词（留空则使用班级提示词）</label>
        <textarea id="agentPrompt" rows="3" style="margin-bottom:10px"></textarea>
        <label>绑定技能（启用中的技能将整段注入回答）</label>
        <div class="checks" id="agentSkillChecks"></div>
        <label>限定检索材料（不选 = 检索本班全部）</label>
        <div class="checks" id="agentMaterialChecks"></div>
        <label style="display:flex;align-items:center;gap:6px;margin-top:6px"><input type="checkbox" id="agentEnabled" checked> 启用该智能体（学生可见）</label>
        <div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <button class="btn" type="button" onclick="submitAgent()">保存智能体</button>
          <span class="err-msg" id="agentErr" style="margin:0"></span>
          <span class="success-msg" id="agentOk"></span>
        </div>
      </div>
    </div>
  </div>

  <div class="card" id="mcpCard" style="display:none">
    <div class="card-header">🔌 MCP 工具服务（仅教师）</div>
    <div class="card-body">
      <div class="cfg-row">
        <label>已登记的 MCP 服务器（令牌只存服务端，任何响应只含「是否已配令牌」）</label>
        <div id="mcpServerList"></div>
      </div>
      <div class="cfg-row">
        <label>登记新服务器（名称同班唯一；Base URL 为 Compose 内网地址，如 http://mcp-demo:8090）</label>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
          <input type="text" id="mcpName" placeholder="名称，如 campus-tools" style="flex:1;min-width:160px">
          <input type="text" id="mcpBaseUrl" placeholder="Base URL，如 http://mcp-demo:8090" style="flex:2;min-width:220px">
          <input type="password" id="mcpToken" placeholder="Bearer 令牌（提交后清空不回显）" autocomplete="new-password" style="flex:1.5;min-width:200px">
          <button class="btn" type="button" onclick="submitMcpServer(false)">登记</button>
        </div>
        <div style="margin-top:6px">
          <span class="err-msg" id="mcpErr" style="margin:0"></span>
          <span class="success-msg" id="mcpOk"></span>
        </div>
      </div>
      <hr style="border:none;border-top:1px solid #f0e6e4;margin:16px 0">
      <div class="cfg-row">
        <label>最近的 MCP 工具调用记录（工具@服务器 / 状态 / 用户 / 会话 / 轮次 / 时间）</label>
        <div id="mcpCallLogs"><div class="empty" style="padding:8px 0">加载中...</div></div>
      </div>
    </div>
  </div>
</div>

<script>
const TOKEN_KEY = 'cc_token';
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function gotoLogin() {
  clearToken();
  window.location.href = '/login?next=' + encodeURIComponent(location.pathname || '/dashboard');
}

// 统一 API 封装：自动携带 Authorization: Bearer；401 时清 token 回登录页
async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  const token = getToken();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 401) { gotoLogin(); throw new Error('unauthorized'); }
  return res;
}

async function logout() {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) { /* 已跳转 */ }
  clearToken();
  window.location.href = '/login';
}

async function init() {
  if (!getToken()) { window.location.href = '/login?next=/dashboard'; return; }
  try {
    const res = await api('/auth/me');
    if (!res.ok) { gotoLogin(); return; }
    const data = await res.json();
    const user = data.user;
    const uid = user.userId || user.id;
    document.getElementById('username').textContent = user.role === 'teacher' ? '👨‍🏫 ' + uid + '号教师' : '👨‍🎓 ' + uid + '号学生';
    document.getElementById('role').textContent = user.role === 'teacher' ? '教师' : '学生';

    // 上传区仅教师可见
    if (user.role === 'teacher') {
      document.getElementById('uploadArea').style.display = 'block';
      document.getElementById('configCard').style.display = 'block';
      document.getElementById('mcpCard').style.display = 'block';
      await loadConfig();
      await loadMcp();
    }

    await loadMaterials();
  } catch (e) { /* api() 已在 401 时跳转 */ }
}

async function loadMaterials() {
  try {
    const res = await api('/materials');
    const data = await res.json();
    const list = document.getElementById('materialList');
    if (!data.materials || data.materials.length === 0) {
      list.innerHTML = '<div class="empty">暂无材料</div>';
      return;
    }
    list.innerHTML = data.materials.map(m => `
      <div class="material-item">
        <div>
          <div class="name">${escapeHtml(m.filename)}</div>
          <div class="meta">上传者: ${m.uploader_user_id} | 大小: ${formatSize(m.size)} | ${m.mime || ''}</div>
        </div>
        <a class="download-btn" href="#" data-id="${m.id}" data-name="${escapeHtml(m.filename)}" onclick="downloadMaterial(event)">下载</a>
      </div>
    `).join('');
  } catch (e) {
    document.getElementById('materialList').innerHTML = '<div class="empty">加载失败</div>';
  }
}

// 浏览器导航请求无法携带 Authorization 头：下载/查看一律 fetch → blob
async function downloadMaterial(ev) {
  const a = ev.target.closest('a');
  const id = a.dataset.id;
  const name = a.dataset.name || ('material-' + id + '.txt');
  try {
    const res = await api('/materials/' + id + '/download');
    if (!res.ok) { alert('下载失败: ' + res.status); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const tmp = document.createElement('a');
    tmp.href = url; tmp.download = name;
    document.body.appendChild(tmp); tmp.click(); tmp.remove();
    URL.revokeObjectURL(url);
  } catch (e) { /* 401 已跳转 */ }
}

async function openMaterial(id) {
  try {
    const res = await api('/materials/' + id + '/download');
    if (!res.ok) { alert('打开失败: ' + res.status); return; }
    const blob = await res.blob();
    window.open(URL.createObjectURL(blob), '_blank');
  } catch (e) { /* 401 已跳转 */ }
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('uploadErr');
  const okEl = document.getElementById('uploadOk');
  errEl.textContent = '';
  okEl.textContent = '';
  const formData = new FormData(e.target);
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  btn.textContent = '上传中...';
  try {
    const res = await api('/materials', {method: 'POST', body: formData});
    if (res.ok) {
      const data = await res.json();
      okEl.textContent = '上传成功: ' + data.filename;
      e.target.reset();
      await loadMaterials();
    } else {
      const data = await res.json();
      errEl.textContent = '上传失败: ' + (data.error || '未知错误');
    }
  } catch (e) {
    errEl.textContent = '上传失败: 网络错误';
  }
  btn.disabled = false;
  btn.textContent = '上传';
});

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

async function doSearch() {
  const query = document.getElementById('searchQuery').value.trim();
  const mode = document.getElementById('searchMode').value;
  const errEl = document.getElementById('searchErr');
  const box = document.getElementById('searchResults');
  errEl.textContent = '';
  box.innerHTML = '<div class="empty">检索中...</div>';
  try {
    const res = await api('/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query, mode})
    });
    const data = await res.json();
    if (!res.ok) {
      box.innerHTML = '';
      errEl.textContent = '检索失败: ' + (data.error || '未知错误') +
        (res.status === 503 ? '（向量/网关暂不可用，可改用关键字检索）' : '');
      return;
    }
    if (!data.hits || data.hits.length === 0) {
      box.innerHTML = '<div class="empty">' + escapeHtml(data.message || '资料中未找到相关内容') + '</div>';
      return;
    }
    box.innerHTML = data.hits.map(h => `
      <div class="hit-item">
        <div class="hit-title">📄 ${escapeHtml(h.materialTitle)} <span style="font-weight:normal;color:#999">#切片${h.chunkIndex}</span></div>
        <div class="hit-meta">字符区间 ${h.charStart}–${h.charEnd}</div>
        <div class="hit-excerpt">${escapeHtml(h.excerpt)}</div>
        <a href="#" onclick="openMaterial(${h.materialId}); return false;">打开材料 →</a>
      </div>
    `).join('');
  } catch (e) {
    box.innerHTML = '';
    errEl.textContent = '检索失败: 网络错误';
  }
}

async function doAsk() {
  const question = document.getElementById('askQuestion').value.trim();
  const errEl = document.getElementById('askErr');
  const ansEl = document.getElementById('answerText');
  const citeEl = document.getElementById('citeList');
  errEl.textContent = '';
  citeEl.innerHTML = '';
  if (!question) { errEl.textContent = '请输入问题'; return; }
  ansEl.style.display = 'block';
  ansEl.textContent = '思考中...';
  try {
    const res = await api('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question})
    });
    const data = await res.json();
    if (!res.ok) {
      ansEl.style.display = 'none';
      errEl.textContent = '问答失败: ' + (data.error || '未知错误') +
        (res.status === 503 ? '（模型网关暂不可用）' : '');
      return;
    }
    ansEl.textContent = data.answer;
    citeEl.innerHTML = (data.citations || []).map(c =>
      `<a href="#" onclick="openMaterial(${c.materialId}); return false;">[${c.ref}] ${escapeHtml(c.materialTitle)} #切片${c.chunkIndex}</a>`
    ).join('');
  } catch (e) {
    ansEl.style.display = 'none';
    errEl.textContent = '问答失败: 网络错误';
  }
}

document.getElementById('searchQuery').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});
document.getElementById('askQuestion').addEventListener('keydown', e => {
  if (e.key === 'Enter') doAsk();
});

// ============ 第5课：解题助手（SSE 流式对话） ============
let agentsCache = [];
let currentConvId = null;

async function initAssistant() {
  try {
    const res = await api('/api/agents');
    const data = await res.json();
    agentsCache = data.agents || [];
    const sel = document.getElementById('agentSelect');
    if (agentsCache.length === 0) {
      sel.innerHTML = '<option value="">暂无可用智能体</option>';
      document.getElementById('convList').innerHTML = '<div class="empty">教师尚未配置智能体</div>';
      return;
    }
    sel.innerHTML = agentsCache.map(a =>
      `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
    await loadConversations();
  } catch (e) { /* 401 已跳转 */ }
}

function onAgentChange() {
  loadConversations();
}

async function loadConversations() {
  const box = document.getElementById('convList');
  try {
    const res = await api('/api/conversations');
    const data = await res.json();
    const convs = data.conversations || [];
    if (convs.length === 0) {
      box.innerHTML = '<div class="empty" style="padding:18px 0">还没有会话<br>点击上方"+ 新会话"</div>';
      return;
    }
    box.innerHTML = convs.map(c => `
      <div class="conv-item ${c.id === currentConvId ? 'active' : ''}" onclick="openConversation(${c.id})">
        ${escapeHtml(c.title || '(未命名会话)')}
        <span class="conv-agent">${escapeHtml(c.agentName || '')}</span>
      </div>`).join('');
  } catch (e) {
    box.innerHTML = '<div class="empty">加载失败</div>';
  }
}

async function newConversation() {
  const agentId = parseInt(document.getElementById('agentSelect').value, 10);
  if (!agentId) return;
  try {
    const res = await api('/api/conversations', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({agent_id: agentId})
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); alert('创建会话失败: ' + (d.error || res.status)); return; }
    await loadConversations();
    const data = await res.json();
    await openConversation(data.conversation.id);
  } catch (e) { /* 401 已跳转 */ }
}

function renderMessage(m) {
  const chatBox = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'msg ' + m.role;
  let inner = '<div class="bubble">' + escapeHtml(m.content) + '</div>';
  const cites = (m.role === 'assistant' && m.citations || []);
  if (cites.length > 0) {
    inner += '<div class="cites">' + cites.map(c =>
      `<a href="#" onclick="openMaterial(${c.materialId}); return false;">[${c.ref}] ${escapeHtml(c.materialTitle)} #切片${c.chunkIndex}</a>`
    ).join('') + '</div>';
  }
  if (m.role === 'assistant' && m.skillName) {
    inner = '<div><span class="skill-tag">技能: ' + escapeHtml(m.skillName) + '</span></div>' + inner;
  }
  div.innerHTML = '<div>' + inner + '</div>';
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
  return div;
}

async function openConversation(convId) {
  currentConvId = convId;
  const chatBox = document.getElementById('chatBox');
  chatBox.innerHTML = '<div class="empty">加载中...</div>';
  try {
    const res = await api('/api/conversations/' + convId);
    if (!res.ok) { chatBox.innerHTML = '<div class="empty">会话不存在或无权访问</div>'; return; }
    const data = await res.json();
    chatBox.innerHTML = '';
    (data.messages || []).forEach(renderMessage);
    if (!(data.messages || []).length) {
      chatBox.innerHTML = '<div class="empty">向解题助手提出你的问题吧</div>';
    }
    document.getElementById('chatInput').disabled = false;
    document.getElementById('chatSendBtn').disabled = false;
    await loadConversations();
  } catch (e) { /* 401 已跳转 */ }
}

async function sendChatMessage() {
  if (!currentConvId) return;
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSendBtn');
  const errEl = document.getElementById('chatErr');
  const content = input.value.trim();
  if (!content) return;
  errEl.textContent = '';
  input.value = '';
  input.disabled = true; sendBtn.disabled = true; sendBtn.textContent = '回答中...';
  const chatBox = document.getElementById('chatBox');
  if (chatBox.querySelector('.empty')) chatBox.innerHTML = '';
  renderMessage({role: 'user', content});
  const asst = renderMessage({role: 'assistant', content: '', citations: []});
  const bubble = asst.querySelector('.bubble');
  bubble.textContent = '思考中...';
  let text = '';
  let interrupted = false;
  try {
    const res = await api('/api/conversations/' + currentConvId + '/messages', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content})
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      asst.remove();
      errEl.textContent = '发送失败: ' + (d.error || res.status) +
        (res.status === 503 ? '（检索/模型网关暂不可用）' : '') +
        (res.status === 404 ? '（智能体已停用或会话不存在）' : '');
      input.disabled = false; sendBtn.disabled = false; sendBtn.textContent = '发送';
      return;
    }
    // 读取 SSE 流：event meta（citations，确有调用时含 tool_calls）→ delta*（增量）→ done
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let citations = [];
    let toolCalls = [];
    let done = false;
    const handleFrame = (frame) => {
      const lines = frame.split('\\n');
      const evLine = lines.find(l => l.startsWith('event:'));
      const dataLine = lines.find(l => l.startsWith('data:'));
      if (!dataLine) return;
      let payload;
      try { payload = JSON.parse(dataLine.slice(5).trim()); } catch (e) { return; }
      const ev = evLine ? evLine.slice(6).trim() : '';
      if (ev === 'meta') {
        citations = payload.citations || [];
        // 第6课：工具调用事件先于正文——meta 一到就记录，流结束后渲染工具栏
        (payload.tool_calls || []).forEach(tc => {
          const label = tc.status === 'ok' ? '✓ 已执行' : (tc.status === 'denied' ? '✕ 被拒' : '⚠ 出错');
          toolCalls.push({ref: tc.ref, status: tc.status, text: tc.text, label});
        });
      } else if (ev === 'delta') {
        if (text === '') bubble.textContent = '';
        text += payload.text || '';
        bubble.textContent = text;
        chatBox.scrollTop = chatBox.scrollHeight;
      } else if (ev === 'done') {
        done = true;
      }
    };
    while (true) {
      const {value, done: rdDone} = await reader.read();
      if (rdDone) break;
      buf += decoder.decode(value, {stream: true});
      const frames = buf.split('\\n\\n');
      buf = frames.pop();
      frames.forEach(handleFrame);
    }
    if (buf.trim()) handleFrame(buf);
    if (!done) {
      interrupted = true;
      bubble.textContent = text + (text ? '\\n\\n（回答中断）' : '');
      if (!text) asst.remove();
    }
    if (toolCalls.length > 0 && asst.parentNode) {
      asst.querySelector('.bubble').insertAdjacentHTML('beforebegin', '<div class="tool-calls">' +
        toolCalls.map(t =>
          `<div class="tool-call ${t.status}"><span class="tool-ref">🔧 ${escapeHtml(t.ref)}</span>` +
          `<span class="tool-status">${escapeHtml(t.label)}</span>` +
          (t.text ? `<span class="tool-text" title="${escapeHtml(t.text)}">${escapeHtml(t.text)}</span>` : '') +
          '</div>'
        ).join('') + '</div>');
    }
    if (citations.length > 0 && asst.parentNode) {
      asst.querySelector('.bubble').insertAdjacentHTML('afterend', '<div class="cites">' +
        citations.map(c =>
          `<a href="#" onclick="openMaterial(${c.materialId}); return false;">[${c.ref}] ${escapeHtml(c.materialTitle)} #切片${c.chunkIndex}</a>`
        ).join('') + '</div>');
    }
  } catch (e) {
    if (asst.parentNode) asst.remove();
    errEl.textContent = '发送失败: 网络错误';
  }
  input.disabled = false; sendBtn.disabled = false; sendBtn.textContent = '发送';
  await loadConversations();
}

document.getElementById('chatInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') sendChatMessage();
});

// ============ 第5课：教师智能体配置 ============
let skillsCache = [];
let materialsCache = [];
let editingSkillId = null;
let editingAgentId = null;

async function loadConfig() {
  try {
    const [promptRes, skillRes, matRes, agentRes] = await Promise.all([
      api('/api/prompt'), api('/api/skills'), api('/materials'), api('/api/agents')
    ]);
    const promptData = await promptRes.json();
    document.getElementById('promptBody').value = promptData.body || '';
    skillsCache = (await skillRes.json()).skills || [];
    materialsCache = (await matRes.json()).materials || [];
    renderSkillList();
    const agents = (await agentRes.json()).agents || [];
    agentsCache = agents;
    const sel = document.getElementById('agentEditSelect');
    sel.innerHTML = '<option value="">— 新建智能体 —</option>' +
      agents.map(a => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
    renderBindingChecks({skill_ids: [], material_ids: []});
  } catch (e) { /* 401 已跳转 */ }
}

function renderSkillList() {
  const box = document.getElementById('skillList');
  if (!skillsCache.length) { box.innerHTML = '<div class="empty" style="padding:12px 0">暂无技能，用下方文本框创建</div>'; return; }
  box.innerHTML = skillsCache.map(s => `
    <div class="skill-item">
      <div>${escapeHtml(s.name)}
        <span class="tag ${s.enabled ? 'on' : ''}">${s.enabled ? '启用中' : '已停用'}</span>
        ${s.subject ? `<span class="tag">${escapeHtml(s.subject)}</span>` : ''}
      </div>
      <div class="ops">
        <button class="btn secondary small" type="button" onclick="editSkill(${s.id})">编辑</button>
        <button class="btn secondary small" type="button" onclick="deleteSkill(${s.id})">删除</button>
      </div>
    </div>`).join('');
}

function renderBindingChecks(agent) {
  document.getElementById('agentSkillChecks').innerHTML = skillsCache
    .filter(s => s.enabled || (agent.skill_ids || []).includes(s.id))
    .map(s => `<label><input type="checkbox" class="skill-check" value="${s.id}" ${(agent.skill_ids || []).includes(s.id) ? 'checked' : ''}> ${escapeHtml(s.name)}${s.enabled ? '' : '（已停用）'}</label>`)
    .join('') || '<span style="color:#aa9999;font-size:12px">暂无技能，先在上方创建</span>';
  document.getElementById('agentMaterialChecks').innerHTML = materialsCache
    .map(m => `<label><input type="checkbox" class="material-check" value="${m.id}" ${(agent.material_ids || []).includes(m.id) ? 'checked' : ''}> ${escapeHtml(m.filename)}</label>`)
    .join('') || '<span style="color:#aa9999;font-size:12px">本班暂无材料</span>';
}

async function savePrompt() {
  const errEl = document.getElementById('promptErr');
  const okEl = document.getElementById('promptOk');
  errEl.textContent = ''; okEl.textContent = '';
  try {
    const res = await api('/api/prompt', {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({body: document.getElementById('promptBody').value})
    });
    const d = await res.json().catch(() => ({}));
    if (res.ok) { okEl.textContent = '已保存，从下一轮回答生效'; }
    else { errEl.textContent = '保存失败: ' + (d.error || res.status); }
  } catch (e) { errEl.textContent = '保存失败: 网络错误'; }
}

function editSkill(id) {
  const s = skillsCache.find(x => x.id === id);
  if (!s) return;
  editingSkillId = id;
  document.getElementById('skillSource').value = s.source;
  document.getElementById('skillUpdateBtn').style.display = '';
  document.getElementById('skillCancelBtn').style.display = '';
  document.getElementById('skillErr').textContent = '';
  document.getElementById('skillOk').textContent = '';
  document.getElementById('skillSource').scrollIntoView({behavior: 'smooth', block: 'center'});
}

function resetSkillEditor() {
  editingSkillId = null;
  document.getElementById('skillSource').value = '';
  document.getElementById('skillUpdateBtn').style.display = 'none';
  document.getElementById('skillCancelBtn').style.display = 'none';
  document.getElementById('skillErr').textContent = '';
  document.getElementById('skillOk').textContent = '';
}

async function submitSkill(isUpdate) {
  const errEl = document.getElementById('skillErr');
  const okEl = document.getElementById('skillOk');
  errEl.textContent = ''; okEl.textContent = '';
  const source = document.getElementById('skillSource').value;
  try {
    const res = isUpdate
      ? await api('/api/skills/' + editingSkillId, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({source})})
      : await api('/api/skills', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({source})});
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      okEl.textContent = isUpdate ? '已更新' : '已创建: ' + (d.skill ? d.skill.name : '');
      resetSkillEditor();
      await loadConfig();
    } else {
      errEl.textContent = (isUpdate ? '更新失败: ' : '创建失败: ') + (d.error || res.status);
    }
  } catch (e) { errEl.textContent = '提交失败: 网络错误'; }
}

async function deleteSkill(id) {
  if (!confirm('删除该技能？已绑定它的智能体会同时解除绑定。')) return;
  try {
    const res = await api('/api/skills/' + id, {method: 'DELETE'});
    if (res.ok) { await loadConfig(); }
    else { const d = await res.json().catch(() => ({})); alert('删除失败: ' + (d.error || res.status)); }
  } catch (e) { /* 401 已跳转 */ }
}

function loadAgentEditor() {
  const idVal = document.getElementById('agentEditSelect').value;
  document.getElementById('agentErr').textContent = '';
  document.getElementById('agentOk').textContent = '';
  if (!idVal) { resetAgentEditor(); return; }
  const a = agentsCache.find(x => x.id === parseInt(idVal, 10));
  if (!a) return;
  editingAgentId = a.id;
  document.getElementById('agentName').value = a.name;
  document.getElementById('agentPrompt').value = a.prompt || '';
  document.getElementById('agentEnabled').checked = !!a.enabled;
  renderBindingChecks(a);
}

function resetAgentEditor() {
  editingAgentId = null;
  document.getElementById('agentEditSelect').value = '';
  document.getElementById('agentName').value = '';
  document.getElementById('agentPrompt').value = '';
  document.getElementById('agentEnabled').checked = true;
  document.getElementById('agentErr').textContent = '';
  document.getElementById('agentOk').textContent = '';
  renderBindingChecks({skill_ids: [], material_ids: []});
}

async function submitAgent() {
  const errEl = document.getElementById('agentErr');
  const okEl = document.getElementById('agentOk');
  errEl.textContent = ''; okEl.textContent = '';
  const name = document.getElementById('agentName').value.trim();
  if (!name) { errEl.textContent = '请填写智能体名称'; return; }
  const skill_ids = Array.from(document.querySelectorAll('.skill-check:checked')).map(x => parseInt(x.value, 10));
  const material_ids = Array.from(document.querySelectorAll('.material-check:checked')).map(x => parseInt(x.value, 10));
  const payload = {
    name,
    prompt: document.getElementById('agentPrompt').value,
    skill_ids, material_ids,
    enabled: document.getElementById('agentEnabled').checked
  };
  try {
    const res = editingAgentId
      ? await api('/api/agents/' + editingAgentId, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})
      : await api('/api/agents', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      okEl.textContent = '已保存';
      resetAgentEditor();
      await loadConfig();
      await initAssistant();
    } else {
      errEl.textContent = '保存失败: ' + (d.error || res.status);
    }
  } catch (e) { errEl.textContent = '保存失败: 网络错误'; }
}

// ============ 第6课：MCP 工具服务管理 ============
let mcpServersCache = [];

async function loadMcp() {
  if (!document.getElementById('mcpCard')) return;
  await renderMcpServers();
  await loadMcpCallLogs();
}

async function renderMcpServers() {
  const box = document.getElementById('mcpServerList');
  try {
    const res = await api('/api/mcp/servers');
    const servers = (await res.json()).servers || [];
    mcpServersCache = servers;
    // 已连接的服务器附带拉取缓存中的工具清单
    await Promise.all(servers.filter(s => s.status === 'connected').map(async s => {
      try {
        const tr = await api(`/api/mcp/servers/${s.id}/tools`);
        s.tools = (await tr.json()).tools || [];
      } catch (e) { s.tools = []; }
    }));
    if (!servers.length) {
      box.innerHTML = '<div class="empty" style="padding:8px 0">本班尚未登记 MCP 服务器</div>';
      return;
    }
    box.innerHTML = servers.map(s => {
      const statusTag = s.status === 'connected'
        ? '<span class="tag on">已连接 · ' + (s.toolsCount || 0) + ' 个工具</span>'
        : '<span class="tag">未连接</span>';
      const toolRows = (s.tools || []).map(t =>
        `<div style="font-size:12px;color:#7a6a66;margin:3px 0 0 12px">• <b>${escapeHtml(t.name)}</b> — ${escapeHtml(t.description || '')}</div>`).join('');
      return `
      <div class="skill-item">
        <div>${escapeHtml(s.name)} ${statusTag}
          <span class="tag">${s.hasToken ? '已配令牌' : '未配令牌'}</span>
          <span class="tag" title="${escapeHtml(s.baseUrl)}">${escapeHtml(s.baseUrl)}</span>
        </div>
        <div class="ops">
          <button class="btn secondary small" type="button" onclick="connectMcp(${s.id})">${s.status === 'connected' ? '重新连接' : '连接'}</button>
          ${s.status === 'connected' ? `<button class="btn secondary small" type="button" onclick="disconnectMcp(${s.id})">断开</button>` : ''}
          <button class="btn secondary small" type="button" onclick="deleteMcp(${s.id})">删除</button>
        </div>
        <div id="mcpTools_${s.id}">${toolRows}</div>
      </div>`;
    }).join('');
  } catch (e) { box.innerHTML = '<div class="empty">加载失败</div>'; }
}

async function submitMcpServer() {
  const errEl = document.getElementById('mcpErr');
  const okEl = document.getElementById('mcpOk');
  errEl.textContent = ''; okEl.textContent = '';
  const name = document.getElementById('mcpName').value.trim();
  const baseUrl = document.getElementById('mcpBaseUrl').value.trim();
  const token = document.getElementById('mcpToken').value;
  if (!name || !baseUrl) { errEl.textContent = '名称与 Base URL 必填'; return; }
  try {
    const res = await api('/api/mcp/servers', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, base_url: baseUrl, token: token || undefined})
    });
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      okEl.textContent = '已登记: ' + (d.server ? d.server.name : name);
      document.getElementById('mcpName').value = '';
      document.getElementById('mcpBaseUrl').value = '';
      document.getElementById('mcpToken').value = '';  // 密码框提交后清空不回显
      await renderMcpServers();
    } else {
      errEl.textContent = '登记失败: ' + (d.error || res.status);
    }
  } catch (e) { errEl.textContent = '登记失败: 网络错误'; }
}

async function connectMcp(id) {
  const errEl = document.getElementById('mcpErr');
  errEl.textContent = '';
  try {
    const res = await api(`/api/mcp/servers/${id}/connect`, {method: 'POST'});
    const d = await res.json().catch(() => ({}));
    if (res.ok) {
      errEl.textContent = '';
      await renderMcpServers();
      await loadMcpCallLogs();
    } else {
      errEl.textContent = d.error || ('连接失败 (HTTP ' + res.status + ')');
      await renderMcpServers();
    }
  } catch (e) { errEl.textContent = '连接失败: 网络错误'; }
}

async function disconnectMcp(id) {
  try {
    await api(`/api/mcp/servers/${id}/disconnect`, {method: 'POST'});
    await renderMcpServers();
  } catch (e) { /* 忽略 */ }
}

async function deleteMcp(id) {
  if (!confirm('删除该 MCP 服务器登记？工具缓存将清空，调用记录保留。')) return;
  try {
    await api(`/api/mcp/servers/${id}`, {method: 'DELETE'});
    await renderMcpServers();
  } catch (e) { /* 忽略 */ }
}

async function loadMcpCallLogs() {
  const box = document.getElementById('mcpCallLogs');
  if (!box) return;
  try {
    const res = await api('/api/mcp/call-logs?limit=20');
    const calls = (await res.json()).calls || [];
    if (!calls.length) { box.innerHTML = '<div class="empty" style="padding:8px 0">暂无调用记录</div>'; return; }
    const badge = {ok: '<span class="tag on">成功</span>', denied: '<span class="tag">被拒</span>', error: '<span class="tag">出错</span>'};
    box.innerHTML = calls.map(c => `
      <div class="skill-item" style="display:block">
        <div><b>${escapeHtml(c.ref)}</b> ${badge[c.status] || escapeHtml(c.status)}
          <span class="tag">用户${c.userId}</span>
          <span class="tag">会话#${c.conversationId}</span>
          <span class="tag">第${c.round}轮</span>
          <span style="color:#aa9999;font-size:11px">${escapeHtml((c.createdAt || '').replace('T', ' '))}</span>
        </div>
        ${c.detail ? `<div style="font-size:12px;color:#7a6a66;margin-top:3px">${escapeHtml(String(c.detail).slice(0, 160))}</div>` : ''}
      </div>`).join('');
  } catch (e) { box.innerHTML = '<div class="empty">加载失败</div>'; }
}

async function init() {
  if (!getToken()) { window.location.href = '/login?next=/dashboard'; return; }
  try {
    const res = await api('/auth/me');
    if (!res.ok) { gotoLogin(); return; }
    const data = await res.json();
    const user = data.user;
    const uid = user.userId || user.id;
    document.getElementById('username').textContent = user.role === 'teacher' ? '👨‍🏫 ' + uid + '号教师' : '👨‍🎓 ' + uid + '号学生';
    document.getElementById('role').textContent = user.role === 'teacher' ? '教师' : '学生';

    // 上传区与智能体配置仅教师可见
    if (user.role === 'teacher') {
      document.getElementById('uploadArea').style.display = 'block';
      document.getElementById('configCard').style.display = 'block';
      document.getElementById('mcpCard').style.display = 'block';
      await loadConfig();
      await loadMcp();
    }

    await loadMaterials();
    await initAssistant();
  } catch (e) { /* api() 已在 401 时跳转 */ }
}

init();
</script>
</body></html>
"""


@pages_bp.route("/login", methods=["GET"])
def login_page():
    """登录页面。"""
    return render_template_string(LOGIN_PAGE.replace("__STYLE__", STYLE))


@pages_bp.route("/dashboard", methods=["GET"])
def dashboard_page():
    """Dashboard 外壳（公开）：前端以 localStorage 中的 Bearer token 认证，
    无 token 或受保护 API 返回 401 时由 JS 跳转登录页。"""
    return render_template_string(DASHBOARD_PAGE.replace("__STYLE__", STYLE))


@pages_bp.route("/", methods=["GET"])
def index():
    """根路径重定向到 Dashboard（前端守卫负责未登录跳转）。"""
    return redirect("/dashboard")


@pages_bp.route("/me", methods=["GET"])
def me_page():
    """兼容旧入口，重定向到 Dashboard。"""
    return redirect("/dashboard")
