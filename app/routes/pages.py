"""前端页面：登录、Dashboard（材料列表/上传/下载/检索/问答/退出）。"""
from flask import Blueprint, redirect, render_template_string

pages_bp = Blueprint("pages", __name__)

STYLE = """
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #333; }
  .navbar { background: #2c3e50; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
  .navbar .brand { color: #fff; font-size: 18px; font-weight: bold; }
  .navbar .user-info { color: #ecf0f1; font-size: 14px; }
  .navbar .user-info span.role { background: #27ae60; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px; }
  .navbar .logout-btn { background: #e74c3c; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; margin-left: 16px; }
  .navbar .logout-btn:hover { background: #c0392b; }
  .container { max-width: 900px; margin: 24px auto; padding: 0 16px; }
  .card { background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 16px; overflow: hidden; }
  .card-header { background: #34495e; color: #fff; padding: 12px 20px; font-size: 16px; font-weight: bold; }
  .card-body { padding: 20px; }
  .material-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; }
  .material-item:last-child { border-bottom: none; }
  .material-item .name { font-size: 15px; font-weight: 500; }
  .material-item .meta { font-size: 12px; color: #999; margin-top: 4px; }
  .download-btn { background: #3498db; color: #fff; text-decoration: none; padding: 6px 16px; border-radius: 4px; font-size: 13px; }
  .download-btn:hover { background: #2980b9; }
  .upload-form { margin-top: 16px; }
  .upload-form input[type="file"] { margin-right: 8px; }
  .upload-form button { background: #27ae60; color: #fff; border: none; padding: 8px 24px; border-radius: 4px; cursor: pointer; }
  .upload-form button:hover { background: #229954; }
  .upload-form button:disabled { background: #95a5a6; cursor: not-allowed; }
  .err-msg { color: #e74c3c; font-size: 14px; margin-top: 8px; }
  .success-msg { color: #27ae60; font-size: 14px; margin-top: 8px; }
  .empty { text-align: center; color: #999; padding: 40px 0; }
  .ask-row, .search-row { display: flex; gap: 8px; }
  .ask-row input, .search-row input { flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .search-row select { padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .ask-row button, .search-row button { background: #8e44ad; color: #fff; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; white-space: nowrap; }
  .ask-row button:hover, .search-row button:hover { background: #7d3c98; }
  .ask-row button:disabled, .search-row button:disabled { background: #95a5a6; cursor: not-allowed; }
  .hit-item { padding: 12px; border: 1px solid #eee; border-radius: 6px; margin-bottom: 10px; }
  .hit-item .hit-title { font-weight: 600; font-size: 14px; }
  .hit-item .hit-meta { font-size: 12px; color: #999; margin: 4px 0; }
  .hit-item .hit-excerpt { font-size: 13px; color: #555; line-height: 1.6; }
  .hit-item a { font-size: 12px; color: #3498db; }
  #answerText { background: #f8f9fa; border-left: 4px solid #8e44ad; padding: 12px; border-radius: 4px; font-size: 14px; line-height: 1.7; margin-top: 12px; white-space: pre-wrap; }
  .cite-list { margin-top: 10px; font-size: 12px; color: #666; }
  .cite-list a { color: #3498db; margin-right: 12px; }
  .login-box { max-width: 400px; margin: 80px auto; background: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); padding: 40px; }
  .login-box h2 { text-align: center; margin-bottom: 24px; color: #2c3e50; }
  .login-box label { display: block; margin-bottom: 6px; font-size: 14px; color: #555; }
  .login-box input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; margin-bottom: 16px; }
  .login-box button { width: 100%; padding: 12px; background: #2c3e50; color: #fff; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
  .login-box button:hover { background: #34495e; }
  .login-box .err { color: #e74c3c; text-align: center; margin-top: 12px; }
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
