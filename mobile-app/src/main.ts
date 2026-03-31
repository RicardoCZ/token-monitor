// Token Monitor Mobile App
// 爱丽丝的作品 ✨
// 多用户版本

import './style.css'
import { CapacitorHttp } from '@capacitor/core'
import { Capacitor } from '@capacitor/core'

const app = document.getElementById('app') as HTMLElement

// 默认服务器配置
const DEFAULT_SERVER = 'http://192.168.3.36:5188'

// 服务配置
const SERVICES = {
  minimax: {
    name: 'MiniMax',
    icon: '🍊',
    loginUrl: 'https://platform.minimaxi.com/user-center/payment/token-plan',
    cookieDomains: 'minimaxi.com,minimax.com'
  },
  xfyun: {
    name: '讯飞星辰',
    icon: '🔵',
    loginUrl: 'https://maas.xfyun.cn/packageSubscription',
    cookieDomains: 'xfyun.cn,xfyun.com'
  }
}

// 自定义 WebView 插件
interface WebViewPluginInterface {
  openLogin(options: { url: string; cookieDomain?: string; cookieDomains?: string }): Promise<void>
  getExtractedCookies(): Promise<{ cookies?: string; pageData?: string }>
  clearExtractedCookies(): Promise<void>
}
const WebViewPlugin = Capacitor.registerPlugin('WebViewPlugin') as WebViewPluginInterface

type HistoryQuery = {
  limit: number
  offset: number
  metric_key?: string
  start_at?: string
  end_at?: string
}

type HistoryResponse = {
  source?: string
  pagination?: {
    limit?: number
    offset?: number
    returned?: number
    total?: number
    has_more?: boolean
  }
  filters?: {
    metric_key?: string | null
    start_at?: string | null
    end_at?: string | null
  }
  items?: Array<{
    metric_key?: string
    collected_at?: string
    normalized_payload?: Record<string, unknown>
  }>
}

type ToastVariant = 'ok' | 'err' | 'info'

function showToast(message: string, variant: ToastVariant = 'info'): void {
  document.getElementById('tm-toast-root')?.remove()
  const el = document.createElement('div')
  el.id = 'tm-toast-root'
  el.className = `tm-toast tm-toast--${variant}`
  el.textContent = message
  document.body.appendChild(el)
  requestAnimationFrame(() => el.classList.add('tm-toast--visible'))
  window.setTimeout(() => {
    el.classList.remove('tm-toast--visible')
    window.setTimeout(() => el.remove(), 280)
  }, 2600)
}

function toRecord(data: unknown): Record<string, unknown> {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data) as Record<string, unknown>
      return parsed || {}
    } catch {
      return {}
    }
  }
  if (data && typeof data === 'object') {
    return data as Record<string, unknown>
  }
  return {}
}

// 获取保存的服务器地址
function getServerUrl(): string {
  return localStorage.getItem('serverUrl') || DEFAULT_SERVER
}

// 保存服务器地址
function setServerUrl(url: string): void {
  localStorage.setItem('serverUrl', url)
}

// 获取保存的 Token
function getToken(): string | null {
  return localStorage.getItem('token')
}

// 保存 Token
function setToken(token: string): void {
  localStorage.setItem('token', token)
}

// 清除 Token
function clearToken(): void {
  localStorage.removeItem('token')
}

// 检查登录状态
async function checkAuth(): Promise<boolean> {
  const token = getToken()
  if (!token) return false
  
  try {
    const resp = await CapacitorHttp.request({
      method: 'GET',
      url: `${getServerUrl()}/auth/me`,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    })
    return resp.status === 200
  } catch {
    return false
  }
}

function parseHasAdminFromSetupResponse(resp: { status: number; data: unknown }): boolean | null {
  if (resp.status !== 200) return null
  const d = resp.data
  if (d && typeof d === 'object' && d !== null && 'hasAdmin' in d) {
    return !!(d as { hasAdmin: boolean }).hasAdmin
  }
  if (typeof d === 'string') {
    try {
      const j = JSON.parse(d) as { hasAdmin?: boolean }
      return j.hasAdmin === undefined ? null : !!j.hasAdmin
    } catch {
      return null
    }
  }
  return null
}

/** true = 已有管理员或请求失败（默认走登录以避免卡在空白引导） */
async function fetchSetupStatus(): Promise<boolean> {
  try {
    const resp = await CapacitorHttp.request({
      method: 'GET',
      url: `${getServerUrl()}/auth/setup-status`,
      headers: { 'Content-Type': 'application/json' }
    })
    const v = parseHasAdminFromSetupResponse(resp)
    if (v !== null) return v
  } catch {
    /* ignore */
  }
  return true
}

const REG_SETUP_USER = /^[a-zA-Z][a-zA-Z0-9_]{2,19}$/

function validateSetupUsername(raw: string): string | null {
  const u = raw.trim()
  if (u.length < 3) return '用户名至少3字符'
  if (u.length > 20) return '用户名最多20字符'
  if (!REG_SETUP_USER.test(u)) return '用户名须字母开头，仅字母数字下划线'
  return null
}

function validateSetupPassword(p: string): string | null {
  if (p.length < 8) return '密码至少8位'
  if (!/[A-Z]/.test(p)) return '密码须包含大写字母'
  if (!/[a-z]/.test(p)) return '密码须包含小写字母'
  if (!/\d/.test(p)) return '密码须包含数字'
  if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/.test(p)) return '密码格式不正确'
  return null
}

function formatSetupFirstError(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((x: { msg?: string; message?: string }) => x.msg || x.message || String(x))
      .join('；')
  }
  return '创建失败'
}

// 首次启动：创建管理员
function renderSetup() {
  const serverUrl = getServerUrl()

  app.innerHTML = `
    <div class="container">
      <header>
        <h1>✨ Token Monitor</h1>
        <p class="subtitle">首次使用 · 创建管理员</p>
      </header>

      <div class="login-section">
        <div class="server-config">
          <label>服务器地址</label>
          <input type="text" id="server-input" value="${serverUrl.replace(/"/g, '&quot;')}" placeholder="http://192.168.3.36:5188">
        </div>
        <p class="hint" style="margin-bottom:12px;color:#aaa;">请设置管理员用户名与密码（与网页注册规则一致）</p>
        <div class="form">
          <input type="text" id="setup-username" placeholder="管理员用户名" autocomplete="username">
          <input type="password" id="setup-password" placeholder="密码（≥8 位，含大写、小写、数字）" autocomplete="new-password">
          <button class="action-btn primary" id="setup-create-btn">创建并进入系统</button>
        </div>
        <p class="hint" style="text-align:center;">
          <button type="button" id="goto-login-btn" class="link-like-btn">已有账号？去登录</button>
        </p>
      </div>
    </div>
  `

  document.getElementById('server-input')?.addEventListener('change', (e) => {
    const input = e.target as HTMLInputElement
    setServerUrl(input.value)
  })

  document.getElementById('goto-login-btn')?.addEventListener('click', () => {
    renderLogin()
  })

  document.getElementById('setup-create-btn')?.addEventListener('click', async () => {
    const username = (document.getElementById('setup-username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('setup-password') as HTMLInputElement).value
    const uErr = validateSetupUsername(username)
    if (uErr) {
      showToast(uErr, 'err')
      return
    }
    const pErr = validateSetupPassword(password)
    if (pErr) {
      showToast(pErr, 'err')
      return
    }
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/setup-first`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password }
      })
      const raw = resp.data as Record<string, unknown> | string
      const data = typeof raw === 'string' ? (JSON.parse(raw) as Record<string, unknown>) : raw
      const token = data?.access_token as string | undefined
      if (resp.status === 200 && token) {
        setToken(token)
        showToast('创建成功', 'ok')
        await renderHome()
        return
      }
      showToast(formatSetupFirstError(data?.detail), 'err')
    } catch (err) {
      showToast('请求失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })
}

// 登录页面
function renderLogin() {
  const serverUrl = getServerUrl()
  
  app.innerHTML = `
    <div class="container">
      <header>
        <h1>✨ Token Monitor</h1>
        <p class="subtitle">API额度实时监控</p>
      </header>
      
      <div class="login-section">
        <div class="server-config">
          <label>服务器地址</label>
          <input type="text" id="server-input" value="${serverUrl}" placeholder="http://192.168.3.36:5188">
        </div>
        
        <div class="tabs">
          <button class="tab active" data-tab="login">登录</button>
          <button class="tab" data-tab="register">注册</button>
        </div>
        
        <div id="login-form" class="form">
          <input type="text" id="username" placeholder="用户名">
          <input type="password" id="password" placeholder="密码">
          <button class="action-btn primary" id="login-btn">登录</button>
        </div>
        
        <div id="register-form" class="form" style="display: none;">
          <input type="text" id="reg-username" placeholder="用户名">
          <input type="password" id="reg-password" placeholder="密码">
          <input type="password" id="reg-password2" placeholder="确认密码">
          <input type="text" id="invite-code" placeholder="邀请码（必填）">
          <button class="action-btn primary" id="register-btn">注册</button>
        </div>
        
        <p class="hint">首次使用请联系管理员获取邀请码</p>
      </div>
    </div>
  `
  
  document.getElementById('server-input')?.addEventListener('change', (e) => {
    const input = e.target as HTMLInputElement
    setServerUrl(input.value)
  })
  
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.getAttribute('data-tab')
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'))
      tab.classList.add('active')
      
      if (tabName === 'login') {
        document.getElementById('login-form')!.style.display = 'block'
        document.getElementById('register-form')!.style.display = 'none'
      } else {
        document.getElementById('login-form')!.style.display = 'none'
        document.getElementById('register-form')!.style.display = 'block'
      }
    })
  })
  
  document.getElementById('login-btn')?.addEventListener('click', async () => {
    const username = (document.getElementById('username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('password') as HTMLInputElement).value
    
    if (!username || !password) {
      showToast('请输入用户名和密码', 'err')
      return
    }
    
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/login`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password }
      })
      
      if (resp.status === 200 && resp.data.access_token) {
        setToken(resp.data.access_token)
        showToast('登录成功', 'ok')
        renderHome()
      } else {
        showToast(String(resp.data.detail || '登录失败'), 'err')
      }
    } catch (err) {
      showToast('登录失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })
  
  document.getElementById('register-btn')?.addEventListener('click', async () => {
    const username = (document.getElementById('reg-username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('reg-password') as HTMLInputElement).value
    const password2 = (document.getElementById('reg-password2') as HTMLInputElement).value
    const inviteCode = (document.getElementById('invite-code') as HTMLInputElement).value.trim()
    
    if (!username || !password) {
      showToast('请输入用户名和密码', 'err')
      return
    }
    if (password !== password2) {
      showToast('两次密码不一致', 'err')
      return
    }
    if (!inviteCode) {
      showToast('请输入邀请码', 'err')
      return
    }
    
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/register`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password, invite_code: inviteCode }
      })
      
      if (resp.status === 200 && resp.data.access_token) {
        setToken(resp.data.access_token)
        showToast('注册成功', 'ok')
        renderHome()
      } else {
        showToast(String(resp.data.detail || '注册失败'), 'err')
      }
    } catch (err) {
      showToast('注册失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })
}

// 主页面
async function renderHome() {
  const isAuth = await checkAuth()
  if (!isAuth) {
    clearToken()
    renderLogin()
    return
  }
  
  app.innerHTML = `
    <div class="container">
      <header>
        <h1>✨ Token Monitor</h1>
        <p class="subtitle">API额度实时监控</p>
        <div class="header-actions">
          <button class="icon-btn" id="logout-btn" title="退出">🚪</button>
        </div>
      </header>
      
      <div class="action-bar">
        <button class="action-btn primary" id="global-refresh">🔄 刷新</button>
        <button class="action-btn secondary" id="global-settings">⚙️ 设置</button>
      </div>
      
      <div class="cards" id="cards">
        <div class="loading">正在加载...</div>
      </div>
    </div>
  `
  
  document.getElementById('logout-btn')?.addEventListener('click', () => {
    clearToken()
    renderLogin()
  })
  
  loadServices()
}

// 加载服务数据
async function loadServices() {
  const cardsEl = document.getElementById('cards')
  if (!cardsEl) return
  
  const serverUrl = getServerUrl()
  const token = getToken()
  
  try {
    const [minimaxResp, xfyunResp] = await Promise.all([
      CapacitorHttp.request({
        method: 'GET',
        url: `${serverUrl}/api/minimax/`,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      }),
      CapacitorHttp.request({
        method: 'GET',
        url: `${serverUrl}/api/xfyun/`,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      })
    ])
    
    const historyByService = await loadLatestHistoryByService(token)
    const cards: string[] = []
    
    if (minimaxResp.status === 200 && minimaxResp.data && !minimaxResp.data.error) {
      const pageInfo = minimaxResp.data.page_info || {}
      const used = pageInfo.used ?? 0
      const total = pageInfo.total ?? 0
      const remain = total - used
      const percent = pageInfo.percent ?? 0
      const resetHours = pageInfo.resetHours || 0
      const resetMinutes = pageInfo.resetMinutes || 0
      
      const resetTime = resetHours > 0 
        ? `${resetHours}小时${resetMinutes}分钟` 
        : `${resetMinutes}分钟`
      const expiresAt = pageInfo.expiresAt || '-'
      
      const minimaxHistory = historyByService.minimax
      cards.push(createCard('minimax', '🍊 MiniMax', 'ok', '正常', [
        { label: 'Token Plan', value: `${total} 次/5小时` },
        { label: '已使用', value: `${used} 次` },
        { label: '剩余', value: `${remain} 次` },
        { label: '使用率', value: `${percent}%` },
        { label: '到期时间', value: expiresAt },
        { label: '重置时间', value: resetTime },
        { label: '最近采集', value: minimaxHistory.collectedAt },
        { label: '历史指标', value: minimaxHistory.metricKey }
      ], String(percent)))
    } else {
      const errorMsg = minimaxResp.data?.error || minimaxResp.data?.detail || '请设置 Cookie'
      cards.push(createErrorCard('minimax', '🍊 MiniMax', errorMsg))
    }
    
    if (xfyunResp.status === 200 && xfyunResp.data && !xfyunResp.data.error) {
      const pageInfo = xfyunResp.data.page_info || {}
      const dailyQuota = pageInfo.dailyQuota || 0
      const dailyUsed = pageInfo.dailyUsed || 0
      const dailyRemain = pageInfo.dailyRemain || 0
      const expiresAt = pageInfo.expiresAt || '-'
      
      const percent = dailyQuota > 0 
        ? ((dailyUsed / dailyQuota) * 100).toFixed(1) 
        : '0'
      
      const xfyunHistory = historyByService.xfyun
      cards.push(createCard('xfyun', '🔵 讯飞星辰 MaaS', 'ok', '正常', [
        { label: '日限额', value: `${dailyQuota} 万 tokens` },
        { label: '已用', value: `${dailyUsed} 万` },
        { label: '剩余', value: `${dailyRemain} 万` },
        { label: '使用率', value: `${percent}%` },
        { label: '到期时间', value: expiresAt },
        { label: '最近采集', value: xfyunHistory.collectedAt },
        { label: '历史指标', value: xfyunHistory.metricKey }
      ], percent))
    } else {
      const errorMsg = xfyunResp.data?.error || xfyunResp.data?.detail || '请设置 Cookie'
      cards.push(createErrorCard('xfyun', '🔵 讯飞星辰 MaaS', errorMsg))
    }
    
    cardsEl.innerHTML = cards.join('')
    
    document.getElementById('global-refresh')?.addEventListener('click', loadServices)
    document.getElementById('global-settings')?.addEventListener('click', showServiceSelector)
    
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    cardsEl.innerHTML = `
      <div class="error">
        <p>连接失败</p>
        <p class="detail">${errorMsg}</p>
        <button id="retry-btn" class="action-btn primary">重试</button>
      </div>
    `
    document.getElementById('retry-btn')?.addEventListener('click', loadServices)
  }
}

function formatHistoryTime(value: string | undefined): string {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return '-'
  return dt.toLocaleString('zh-CN', { hour12: false })
}

function buildHistoryQuery(params: HistoryQuery): string {
  const query = new URLSearchParams({
    limit: String(params.limit),
    offset: String(params.offset)
  })
  if (params.metric_key) query.set('metric_key', params.metric_key)
  if (params.start_at) query.set('start_at', params.start_at)
  if (params.end_at) query.set('end_at', params.end_at)
  return query.toString()
}

async function loadLatestHistoryByService(token: string | null): Promise<Record<string, { collectedAt: string; metricKey: string }>> {
  const empty: Record<string, { collectedAt: string; metricKey: string }> = {
    minimax: { collectedAt: '-', metricKey: '-' },
    xfyun: { collectedAt: '-', metricKey: '-' }
  }
  if (!token) return empty

  try {
    const accountResp = await CapacitorHttp.request({
      method: 'GET',
      url: `${getServerUrl()}/api/accounts`,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    })
    if (accountResp.status !== 200) return empty
    let accounts: Array<Record<string, unknown>> = []
    if (Array.isArray(accountResp.data)) {
      accounts = accountResp.data as Array<Record<string, unknown>>
    } else if (typeof accountResp.data === 'string') {
      try {
        const parsed = JSON.parse(accountResp.data) as unknown
        if (Array.isArray(parsed)) {
          accounts = parsed as Array<Record<string, unknown>>
        } else if (parsed && typeof parsed === 'object' && Array.isArray((parsed as { items?: unknown[] }).items)) {
          accounts = (parsed as { items: Array<Record<string, unknown>> }).items
        }
      } catch {
        accounts = []
      }
    } else {
      const accountData = toRecord(accountResp.data)
      if (Array.isArray(accountData.items)) {
        accounts = accountData.items as Array<Record<string, unknown>>
      }
    }
    const byService: Record<string, { id: number }> = {}
    for (const raw of accounts) {
      const item = raw as Record<string, unknown>
      const sid = String(item.service_id || '').trim()
      const id = Number(item.id)
      if (sid && Number.isFinite(id)) byService[sid] = { id }
    }

    const requests: Array<Promise<void>> = []
    const specs = [
      { sid: 'minimax', metric: 'quota' },
      { sid: 'xfyun', metric: 'daily_quota' }
    ]
    for (const spec of specs) {
      const account = byService[spec.sid]
      if (!account) continue
      const query = buildHistoryQuery({ limit: 1, offset: 0, metric_key: spec.metric })
      requests.push((async () => {
        const historyResp = await CapacitorHttp.request({
          method: 'GET',
          url: `${getServerUrl()}/api/accounts/${account.id}/history?${query}`,
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        })
        if (historyResp.status !== 200) return
        const payload = toRecord(historyResp.data) as HistoryResponse
        const items = Array.isArray(payload.items) ? payload.items : []
        const first = items[0]
        if (!first) return
        empty[spec.sid] = {
          collectedAt: formatHistoryTime(first.collected_at),
          metricKey: String(first.metric_key || spec.metric)
        }
      })())
    }
    await Promise.all(requests)
    return empty
  } catch {
    return empty
  }
}

function normalizeServiceId(id: string | null | undefined): keyof typeof SERVICES | null {
  const k = String(id || '')
    .trim()
    .toLowerCase()
  if (k === 'minimax' || k === 'xfyun') return k
  return null
}

function readGroupIdFromPlugin(result: unknown): string {
  if (!result || typeof result !== 'object') return ''
  const r = result as Record<string, unknown>
  const a = r.groupId ?? r.group_id
  return a != null && String(a).trim() !== '' ? String(a).trim() : ''
}

function getGroupIdInputValue(): string {
  const el = document.getElementById('group-id') as HTMLInputElement | null
  return (el?.value ?? '').trim()
}

/** 与首页卡片一致：重置剩余时间展示为「X小时X分钟」或仅「X分钟」 */
function formatResetTimeRemaining(hours: unknown, minutes: unknown): string {
  const h = Math.max(0, Math.floor(Number(hours) || 0))
  const m = Math.max(0, Math.floor(Number(minutes) || 0))
  if (h <= 0 && m <= 0) return ''
  if (h > 0) return `${h}小时${m}分钟`
  return `${m}分钟`
}

// Cookie 设置页
function renderCookiePage(serviceId: string) {
  if (!app) {
    console.error('[TokenMonitor] #app 不存在，无法渲染')
    return
  }

  const sid = normalizeServiceId(serviceId)
  if (!sid) {
    console.error('[TokenMonitor] renderCookiePage: 非法 serviceId=', JSON.stringify(serviceId))
    return
  }
  const service = SERVICES[sid]
  const showGroupIdBlock = sid === 'minimax'
  const groupIdPanelClass = showGroupIdBlock
    ? 'group-id-input group-id-panel group-id-panel--minimax'
    : 'group-id-input group-id-panel group-id-panel--hidden'

  app.innerHTML = `
    <div class="container">
      <header>
        <button class="back-btn" id="back-btn">← 返回</button>
        <h1>${service.icon} ${service.name}</h1>
        <p class="subtitle">Cookie 设置</p>
      </header>
      
      <div class="cookie-section">
        <div class="info-card">
          <h3>📋 如何获取数据</h3>
          <ol>
            <li>点「打开登录页」，进入平台网页。</li>
            <li>在页面里完成登录。</li>
            <li>在WebView顶部点「提取数据」。</li>
            <li>回到本页，点「自动填充数据」。</li>
            <li>MiniMax 必填 GroupId，并核对 Cookie。</li>
            <li>确认无误后点「保存」。</li>
          </ol>
        </div>
        
        <button class="action-btn primary" id="open-login">
          🌐 打开登录页
        </button>
        
        <button class="action-btn secondary" id="extract-cookie">
          📋 自动填充数据
        </button>

        <div class="${groupIdPanelClass}" id="group-id-section" data-tm="minimax-groupid">
          <label>GroupId <span style="color: #ff6b6b;">*必填（MiniMax）</span></label>
          <input type="text" id="group-id" name="tm-group-id" autocomplete="off" placeholder="提取后自动填入，或手动输入">
          <small style="color: #888;">与 Cookie 分开填写；手动 / 自动保存共用此框</small>
        </div>
        
        <div id="page-info"></div>
        
        <div class="cookie-display" id="cookie-display" style="display: none;">
          <label>提取到的 Cookie：</label>
          <textarea id="cookie-text" readonly></textarea>
          <button class="action-btn primary" id="save-cookie">💾 保存</button>
        </div>
        
        <div class="manual-input">
          <h3>或手动输入 Cookie</h3>
          <textarea id="manual-cookie" placeholder="粘贴 Cookie..."></textarea>
          <button class="action-btn primary" id="save-manual">💾 保存</button>
        </div>
      </div>
    </div>
  `

  let currentPageData: any = null

  document.getElementById('back-btn')?.addEventListener('click', renderHome)
  
  document.getElementById('open-login')?.addEventListener('click', async () => {
    try {
      await WebViewPlugin.openLogin({
        url: service.loginUrl,
        cookieDomain: service.cookieDomains,
        cookieDomains: service.cookieDomains
      })
    } catch (err) {
      console.error('打开登录页失败', err)
    }
  })
  
  document.getElementById('extract-cookie')?.addEventListener('click', async () => {
    try {
      const result = await WebViewPlugin.getExtractedCookies()
      const cookies = (result as { cookies?: string }).cookies ?? ''
      const pageDataStr = (result as { pageData?: string }).pageData ?? '{}'

      let pageData: Record<string, unknown> = {}
      try {
        pageData = JSON.parse(pageDataStr) as Record<string, unknown>
        currentPageData = pageData
      } catch (e) {}

      let groupId = (pageData.groupId != null ? String(pageData.groupId) : '').trim()
      const fromPlugin = readGroupIdFromPlugin(result)
      if (!groupId && fromPlugin) groupId = fromPlugin
      if (!groupId && cookies) {
        const match = cookies.match(/_gc_usr_id_cs0_d0_sec0_part0=([^;]+)/)
        if (match) groupId = match[1]
      }

      if (cookies && cookies.length > 0) {
        const displayEl = document.getElementById('cookie-display')
        const textareaEl = document.getElementById('cookie-text') as HTMLTextAreaElement
        if (displayEl && textareaEl) {
          displayEl.style.display = 'block'
          textareaEl.value = cookies
        }
      }

      if (sid === 'minimax') {
        const groupIdInput = document.getElementById('group-id') as HTMLInputElement
        if (groupIdInput && groupId) {
          groupIdInput.value = groupId
        }
      }
      
      const infoEl = document.getElementById('page-info')
      if (infoEl) {
        let infoHtml = '<div class="page-info">'
        if (groupId) infoHtml += `<p>🆔 GroupId: ${groupId}</p>`
        if (pageData.expiresAt) infoHtml += `<p>📅 截止日期: ${pageData.expiresAt}</p>`
        const resetCombined = formatResetTimeRemaining(
          pageData.resetHours,
          pageData.resetMinutes
        )
        if (resetCombined) {
          infoHtml += `<p>⏰ 重置时间: ${resetCombined}（距下一轮重置）</p>`
        }
        if (pageData.used && pageData.total) infoHtml += `<p>📊 使用量: ${pageData.used}/${pageData.total}</p>`
        infoHtml += '</div>'
        infoEl.innerHTML = infoHtml
      }
      
      if (cookies || groupId) {
        showToast('已自动填充', 'ok')
      } else {
        showToast('未找到可填充数据：请先在 WebView 内点「提取数据」，再回到本页点「自动填充数据」', 'err')
      }
    } catch (err) {
      showToast('提取失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })
  
  document.getElementById('save-cookie')?.addEventListener('click', async () => {
    try {
      const uiCookie =
        (document.getElementById('cookie-text') as HTMLTextAreaElement | null)?.value?.trim() ?? ''
      const gidInput = getGroupIdInputValue()

      let cookiesToSend: string
      let groupIdToSend: string | null

      if (sid === 'minimax') {
        if (!uiCookie || !gidInput) {
          showToast('「提取到的 Cookie」与 GroupId 须同时填写后再保存', 'err')
          return
        }
        cookiesToSend = uiCookie
        groupIdToSend = gidInput
      } else {
        const result = await WebViewPlugin.getExtractedCookies()
        const fromPlugin = (result.cookies as string)?.trim() ?? ''
        cookiesToSend = uiCookie || fromPlugin
        groupIdToSend = null
        if (!cookiesToSend) {
          showToast('没有 Cookie，请先自动填充或手动填写', 'err')
          return
        }
      }

      const token = getToken()
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/api/accounts`,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        data: {
          service_id: sid,
          name: `我的${service.name}`,
          cookies: cookiesToSend,
          group_id: groupIdToSend
        }
      })

      if (resp.status === 200) {
        showToast('保存成功', 'ok')
        await WebViewPlugin.clearExtractedCookies()
        renderHome()
      } else {
        showToast('保存失败：' + (resp.data.detail || '未知错误'), 'err')
      }
    } catch (err) {
      showToast('保存失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })

  document.getElementById('save-manual')?.addEventListener('click', async () => {
    const textarea = document.getElementById('manual-cookie') as HTMLTextAreaElement
    const cookie = textarea.value.trim()
    const gidInput = getGroupIdInputValue()

    if (sid === 'minimax') {
      if (!cookie || !gidInput) {
        showToast('手动 Cookie 与 GroupId 须同时填写后再保存', 'err')
        return
      }
    } else if (!cookie) {
      showToast('请输入 Cookie', 'err')
      return
    }
    
    try {
      const token = getToken()
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/api/accounts`,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        data: {
          service_id: sid,
          name: `我的${service.name}`,
          cookies: cookie,
          group_id: sid === 'minimax' ? gidInput : null
        }
      })

      if (resp.status === 200) {
        showToast('保存成功', 'ok')
        renderHome()
      } else {
        showToast('保存失败：' + (resp.data.detail || '未知错误'), 'err')
      }
    } catch (err) {
      showToast('保存失败：' + (err instanceof Error ? err.message : String(err)), 'err')
    }
  })
}

// 显示服务选择弹窗
function showServiceSelector() {
  app.innerHTML = `
    <div class="container">
      <header>
        <button class="back-btn" id="back-btn">← 返回</button>
        <h1>⚙️ Cookie 设置</h1>
        <p class="subtitle">选择要配置的服务</p>
      </header>
      
      <div class="service-list">
        <button class="service-item" data-service="minimax">
          <span class="service-icon">🍊</span>
          <span class="service-name">MiniMax</span>
        </button>
        <button class="service-item" data-service="xfyun">
          <span class="service-icon">🔵</span>
          <span class="service-name">讯飞星辰 MaaS</span>
        </button>
      </div>
    </div>
  `
  
  document.getElementById('back-btn')?.addEventListener('click', renderHome)
  
  document.querySelectorAll('.service-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const serviceId = btn.getAttribute('data-service')
      if (serviceId) renderCookiePage(serviceId)
    })
  })
}

// 创建卡片 HTML
function createCard(serviceId: string, title: string, badgeClass: string, badgeText: string, stats: {label: string, value: string}[], percent: string) {
  const colorClass = Number(percent) > 80 ? 'red' : Number(percent) > 50 ? 'orange' : 'green'
  return `
    <div class="card" data-service="${serviceId}">
      <div class="card-header">
        <span class="card-title">${title}</span>
        <span class="badge ${badgeClass}">${badgeText}</span>
      </div>
      <div class="card-body">
        ${stats.map(s => `
          <div class="stat">
            <span class="label">${s.label}</span>
            <span class="value">${s.value}</span>
          </div>
        `).join('')}
        <div class="progress-bar">
          <div class="progress-fill ${colorClass}" style="width: ${percent}%"></div>
        </div>
      </div>
    </div>
  `
}

// 创建错误卡片 HTML
function createErrorCard(serviceId: string, title: string, errorMsg: string) {
  return `
    <div class="card" data-service="${serviceId}">
      <div class="card-header">
        <span class="card-title">${title}</span>
        <span class="badge error">需设置</span>
      </div>
      <div class="card-body">
        <p class="error-msg">${errorMsg}</p>
      </div>
    </div>
  `
}

async function bootstrap(): Promise<void> {
  const token = getToken()
  if (token) {
    const ok = await checkAuth()
    if (ok) {
      await renderHome()
      return
    }
    clearToken()
  }
  const hasAdmin = await fetchSetupStatus()
  if (!hasAdmin) {
    renderSetup()
    return
  }
  renderLogin()
}

bootstrap()
