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
    icon: '/icons/minimax.ico',
    loginUrl: 'https://platform.minimaxi.com/user-center/payment/token-plan',
    cookieDomains: 'minimaxi.com,minimax.com'
  },
  xfyun: {
    name: '讯飞',
    icon: '/icons/xfyun.ico',
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

/** 与 backend 服务注册表及 web TMDCore 对齐 */
type MetricDef = { key?: string; label?: string; unit?: string }

type ServiceRegistryItem = {
  id: string
  name: string
  icon?: string
  login_url?: string
  cookie_domains?: string[] | string
  metric_defs?: MetricDef[]
  capabilities?: { requires_group_id?: boolean }
}

type UsageNumbers = {
  used: number
  total: number
  remain: number
  percent: number
  expiresAt: string
  resetHours: number
  resetMinutes: number
  resetCaption: string
}

const FALLBACK_SERVICE_REGISTRY: ServiceRegistryItem[] = [
  {
    id: 'minimax',
    name: 'MiniMax',
    icon: '/icons/minimax.ico',
    login_url: 'https://platform.minimaxi.com/user-center/payment/token-plan',
    cookie_domains: 'minimaxi.com,minimax.com',
    capabilities: { requires_group_id: true },
    metric_defs: [
      { key: 'used', label: '已用额度', unit: 'count' },
      { key: 'total', label: '总额度', unit: 'count' },
      { key: 'percent', label: '使用率', unit: 'percent' }
    ]
  },
  {
    id: 'xfyun',
    name: '讯飞',
    icon: '/icons/xfyun.ico',
    login_url: 'https://maas.xfyun.cn/packageSubscription',
    cookie_domains: 'xfyun.cn,xfyun.com',
    capabilities: { requires_group_id: false },
    metric_defs: [
      { key: 'used', label: '已用额度', unit: 'w' },
      { key: 'total', label: '总额度', unit: 'w' },
      { key: 'percent', label: '使用率', unit: 'percent' }
    ]
  }
]

/** 最近一次成功的注册表（供设置页展示名等使用） */
let cachedServiceRegistry: ServiceRegistryItem[] = []

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

function clearAuthBanner(): void {
  const el = document.getElementById('auth-banner')
  if (!el) return
  el.style.display = 'none'
  el.textContent = ''
  el.className = 'auth-banner'
}

function showAuthBanner(kind: 'err' | 'ok', message: string): void {
  const el = document.getElementById('auth-banner')
  if (!el) return
  el.style.display = 'block'
  el.textContent = message
  el.className = `auth-banner auth-banner--${kind}`
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

function parseJsonBody<T>(raw: unknown): T | null {
  if (raw == null) return null
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  }
  if (typeof raw === 'object') return raw as T
  return null
}

function getNumberValue(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function formatUnit(unit: string | undefined): string {
  const key = String(unit || '').toLowerCase()
  if (!key) return ''
  if (key === 'percent') return '%'
  if (key === 'count') return '次'
  if (key === 'w') return '万'
  return String(unit || '')
}

function normalizeMetricDefs(metricDefs: unknown): Array<{ key: string; label: string; unit: string }> {
  if (!Array.isArray(metricDefs)) return []
  const defs = metricDefs
    .filter((item): item is Record<string, unknown> => item != null && typeof item === 'object')
    .map(item => ({
      key: String(item.key || '').trim(),
      label: String(item.label || item.key || '').trim(),
      unit: String(item.unit || '').trim()
    }))
    .filter(item => item.key)
  const deduped: typeof defs = []
  const seen = new Set<string>()
  for (const item of defs) {
    if (seen.has(item.key)) continue
    seen.add(item.key)
    deduped.push(item)
  }
  return deduped
}

function buildUsageNumbers(data: Record<string, unknown>): UsageNumbers {
  const pageInfo = (data.page_info as Record<string, unknown> | undefined) || {}
  const used = getNumberValue(pageInfo.used)
  const total = getNumberValue(pageInfo.total)
  const remainFromPage = pageInfo.remain
  const remain =
    remainFromPage != null ? getNumberValue(remainFromPage) : Math.max(0, total - used)
  const percentRaw = pageInfo.percent ?? data.percent
  const percent =
    percentRaw != null
      ? getNumberValue(percentRaw)
      : total > 0
        ? (used / total) * 100
        : 0
  const expiresAtRaw =
    pageInfo.expiresAt ??
    pageInfo.expires_at ??
    pageInfo.expireAt ??
    pageInfo.expire_at ??
    data.expiresAt ??
    data.expires_at
  const resetCaptionRaw = pageInfo.resetCaption ?? pageInfo.reset_caption ?? ''
  return {
    used,
    total,
    remain,
    percent,
    expiresAt: expiresAtRaw ? String(expiresAtRaw) : '-',
    resetHours: getNumberValue(pageInfo.resetHours ?? pageInfo.reset_hours),
    resetMinutes: getNumberValue(pageInfo.resetMinutes ?? pageInfo.reset_minutes),
    resetCaption: String(resetCaptionRaw || '').trim()
  }
}

function pickMetricValue(metricKey: string, usage: UsageNumbers): number | null {
  const key = String(metricKey || '').trim().toLowerCase()
  if (key === 'used') return usage.used
  if (key === 'total') return usage.total
  if (key === 'percent') return usage.percent
  if (key === 'remain') return usage.remain
  return null
}

function formatMetricValue(value: number, unit: string, metricKey: string): string {
  const numeric = getNumberValue(value)
  if (String(unit || '').toLowerCase() === 'percent' || String(metricKey || '').toLowerCase().includes('percent')) {
    return `${numeric.toFixed(1)}%`
  }
  const unitText = formatUnit(unit)
  if (!unitText) return `${numeric}`
  return `${numeric} ${unitText}`.trim()
}

function formatResetTime(resetHours: number, resetMinutes: number): string {
  if (resetHours > 0 || resetMinutes > 0) {
    return `${resetHours || 0}小时${resetMinutes || 0}分钟`
  }
  return '-'
}

function buildMetricRows(
  service: ServiceRegistryItem,
  data: Record<string, unknown>
): { rows: Array<{ label: string; value: string }>; usage: UsageNumbers } {
  const usage = buildUsageNumbers(data)
  const defs = normalizeMetricDefs(service.metric_defs)
  const rows: Array<{ label: string; value: string }> = []
  const renderedKeys = new Set<string>()
  for (const def of defs) {
    const value = pickMetricValue(def.key, usage)
    if (value == null) continue
    renderedKeys.add(String(def.key || '').trim().toLowerCase())
    rows.push({
      label: def.label || def.key,
      value: formatMetricValue(value, def.unit, def.key)
    })
  }
  if (!renderedKeys.has('remain')) {
    const totalDef = defs.find(def => String(def.key || '').trim().toLowerCase() === 'total')
    const usedDef = defs.find(def => String(def.key || '').trim().toLowerCase() === 'used')
    const remainUnit = (totalDef && totalDef.unit) || (usedDef && usedDef.unit) || ''
    rows.push({
      label: '剩余',
      value: formatMetricValue(usage.remain, remainUnit, 'remain')
    })
  }
  if (!rows.length) {
    rows.push({ label: '已用', value: `${usage.used}` })
    rows.push({ label: '总量', value: `${usage.total}` })
    rows.push({ label: '剩余', value: `${usage.remain}` })
    rows.push({ label: '使用率', value: `${usage.percent.toFixed(1)}%` })
  }
  return { rows, usage }
}

/** 与 api-dashboard-app.js buildCardDynamicInnerHtml 中指标 + meta 一致 */
function buildMobileCardStats(
  service: ServiceRegistryItem,
  data: Record<string, unknown>
): { stats: Array<{ label: string; value: string }>; percentStr: string } {
  const { rows, usage } = buildMetricRows(service, data)
  const sid = String(service.id || '').toLowerCase()
  const resetValue =
    usage.resetCaption ||
    (sid === 'xfyun' ? '每日 00:00' : '') ||
    formatResetTime(usage.resetHours, usage.resetMinutes)
  const metaRows = [
    { label: '到期时间', value: usage.expiresAt || '-' },
    { label: '重置时间', value: resetValue }
  ]
  return {
    stats: [...rows, ...metaRows],
    percentStr: Math.max(0, Math.min(100, usage.percent)).toFixed(1)
  }
}

function extractApiErrorMessage(data: unknown): string {
  if (!data || typeof data !== 'object') return '加载失败'
  const d = data as Record<string, unknown>
  if (typeof d.detail === 'string') return d.detail
  if (Array.isArray(d.detail)) {
    const parts = d.detail
      .map((e: { msg?: string; message?: string }) => (e && (e.msg || e.message)) || '')
      .filter(Boolean)
    return parts.length ? parts.join(' ') : '请求无效'
  }
  if (d.error) return String(d.error)
  return ''
}

async function fetchServiceRegistry(
  serverUrl: string,
  token: string | null
): Promise<ServiceRegistryItem[]> {
  if (!token) return FALLBACK_SERVICE_REGISTRY
  try {
    const resp = await CapacitorHttp.request({
      method: 'GET',
      url: `${serverUrl}/api/services`,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      }
    })
    if (resp.status !== 200) return FALLBACK_SERVICE_REGISTRY
    const parsed = parseJsonBody<ServiceRegistryItem[]>(resp.data)
    if (!Array.isArray(parsed) || !parsed.length) return FALLBACK_SERVICE_REGISTRY
    return parsed
  } catch {
    return FALLBACK_SERVICE_REGISTRY
  }
}

function escapeHtmlText(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function isServiceIconUrl(icon: string): boolean {
  const t = icon.trim()
  if (!t) return false
  if (t.startsWith('/icons/') || t.startsWith('http://') || t.startsWith('https://')) return true
  return /\.(ico|png|webp|svg|gif)$/i.test(t)
}

/** 与 web TMDCore.renderServiceIconHtml 对齐：路径则 <img>，否则转义作文本（含 emoji） */
function serviceIconHtml(icon: string): string {
  const t = String(icon || '').trim()
  if (!t) return ''
  if (isServiceIconUrl(t)) {
    const safe = escapeHtmlText(t)
    return `<img class="tm-service-icon" src="${safe}" alt="" width="20" height="20" loading="lazy" decoding="async" />`
  }
  return escapeHtmlText(t)
}

function serviceHeadingHtml(icon: string, name: string): string {
  const n = escapeHtmlText(name)
  const ih = serviceIconHtml(icon)
  if (!ih) return n
  return `<span class="service-heading"><span class="service-heading__icon">${ih}</span><span class="service-heading__name">${n}</span></span>`
}

function serviceCardTitle(s: ServiceRegistryItem): string {
  const rawIcon = s.icon != null && String(s.icon).trim() !== '' ? String(s.icon).trim() : ''
  return serviceHeadingHtml(rawIcon, s.name || s.id)
}

function getServiceUiMeta(sid: string): {
  name: string
  icon: string
  loginUrl: string
  cookieDomains: string
} {
  const fromReg = cachedServiceRegistry.find(s => s.id === sid)
  if (fromReg) {
    const domains = fromReg.cookie_domains
    const cookieDomains = Array.isArray(domains) ? domains.join(',') : String(domains || '').trim()
    return {
      name: fromReg.name || sid,
      icon: fromReg.icon != null && String(fromReg.icon).trim() !== '' ? String(fromReg.icon).trim() : '•',
      loginUrl: String(fromReg.login_url || '').trim(),
      cookieDomains
    }
  }
  const fromSeed = FALLBACK_SERVICE_REGISTRY.find(s => s.id === sid)
  if (fromSeed) {
    const domains = fromSeed.cookie_domains
    const cookieDomains = Array.isArray(domains) ? domains.join(',') : String(domains || '').trim()
    return {
      name: fromSeed.name || sid,
      icon: fromSeed.icon != null && String(fromSeed.icon).trim() !== '' ? String(fromSeed.icon).trim() : '•',
      loginUrl: String(fromSeed.login_url || '').trim(),
      cookieDomains
    }
  }
  const fallback = SERVICES[sid as keyof typeof SERVICES]
  if (fallback) {
    return {
      name: fallback.name,
      icon: fallback.icon,
      loginUrl: fallback.loginUrl,
      cookieDomains: fallback.cookieDomains
    }
  }
  return { name: sid, icon: '•', loginUrl: '', cookieDomains: '' }
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
    <div class="auth-screen">
      <div class="auth-card">
        <div class="auth-logo">
          <h1>✨ Token Monitor</h1>
          <p>首次使用 · 创建管理员</p>
        </div>
        <p class="auth-intro">数据库中尚无管理员时，请先创建管理员账号（规则与网页一致），用于登录与发放邀请码。</p>
        <div id="auth-banner" class="auth-banner" role="alert"></div>
        <div class="form-group">
          <label for="server-input">服务器地址</label>
          <input type="text" id="server-input" class="auth-input" value="${serverUrl.replace(/"/g, '&quot;')}" placeholder="http://192.168.x.x:5188" autocomplete="url" inputmode="url">
        </div>
        <div class="form-group">
          <label for="setup-username">管理员用户名</label>
          <input type="text" id="setup-username" class="auth-input" placeholder="字母开头，3–20 位" autocomplete="username">
        </div>
        <div class="form-group">
          <label for="setup-password">密码</label>
          <input type="password" id="setup-password" class="auth-input" placeholder="≥8 位，含大写、小写、数字" autocomplete="new-password">
        </div>
        <button type="button" class="auth-submit" id="setup-create-btn">创建并进入系统</button>
        <p class="auth-footer-link">
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
    clearAuthBanner()
    const username = (document.getElementById('setup-username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('setup-password') as HTMLInputElement).value
    const uErr = validateSetupUsername(username)
    if (uErr) {
      showAuthBanner('err', uErr)
      showToast(uErr, 'err')
      return
    }
    const pErr = validateSetupPassword(password)
    if (pErr) {
      showAuthBanner('err', pErr)
      showToast(pErr, 'err')
      return
    }
    const btn = document.getElementById('setup-create-btn') as HTMLButtonElement
    const idleLabel = '创建并进入系统'
    btn.disabled = true
    btn.textContent = '创建中…'
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/setup-first`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password }
      })
      const data = toRecord(resp.data)
      const token = data.access_token as string | undefined
      if (resp.status === 200 && token) {
        setToken(token)
        showAuthBanner('ok', '创建成功，正在进入…')
        showToast('创建成功', 'ok')
        await renderHome()
        return
      }
      const msg = extractApiErrorMessage(data) || formatSetupFirstError(data.detail)
      showAuthBanner('err', msg || '创建失败')
      showToast(msg || '创建失败', 'err')
    } catch (err) {
      const msg = '请求失败：' + (err instanceof Error ? err.message : String(err))
      showAuthBanner('err', msg)
      showToast(msg, 'err')
    } finally {
      btn.disabled = false
      btn.textContent = idleLabel
    }
  })
}

// 登录页面
function renderLogin() {
  const serverUrl = getServerUrl()

  app.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <div class="auth-logo">
          <h1>✨ Token Monitor</h1>
          <p>API 额度实时监控</p>
        </div>
        <div id="auth-banner" class="auth-banner" role="alert"></div>
        <div class="form-group">
          <label for="server-input">服务器地址</label>
          <input type="text" id="server-input" class="auth-input" value="${serverUrl.replace(/"/g, '&quot;')}" placeholder="http://192.168.x.x:5188" autocomplete="url" inputmode="url">
        </div>
        <div class="auth-tabs" role="tablist">
          <button type="button" class="auth-tab active" data-tab="login" role="tab" aria-selected="true">登录</button>
          <button type="button" class="auth-tab" data-tab="register" role="tab" aria-selected="false">注册</button>
        </div>
        <div id="login-form" class="auth-form">
          <div class="form-group">
            <label for="username">用户名</label>
            <input type="text" id="username" class="auth-input" placeholder="用户名" autocomplete="username">
          </div>
          <div class="form-group">
            <label for="password">密码</label>
            <input type="password" id="password" class="auth-input" placeholder="密码" autocomplete="current-password">
          </div>
          <button type="button" class="auth-submit" id="login-btn">登录</button>
        </div>
        <div id="register-form" class="auth-form" style="display: none;">
          <div class="form-group">
            <label for="reg-username">用户名</label>
            <input type="text" id="reg-username" class="auth-input" placeholder="用户名" autocomplete="username">
          </div>
          <div class="form-group">
            <label for="reg-password">密码</label>
            <input type="password" id="reg-password" class="auth-input" placeholder="密码" autocomplete="new-password">
          </div>
          <div class="form-group">
            <label for="reg-password2">确认密码</label>
            <input type="password" id="reg-password2" class="auth-input" placeholder="再次输入密码" autocomplete="new-password">
          </div>
          <div class="form-group">
            <label for="invite-code">邀请码</label>
            <input type="text" id="invite-code" class="auth-input" placeholder="必填，向管理员索取" autocomplete="one-time-code">
          </div>
          <button type="button" class="auth-submit" id="register-btn">注册</button>
        </div>
        <p class="auth-hint">首次使用请联系管理员获取邀请码</p>
      </div>
    </div>
  `

  document.getElementById('server-input')?.addEventListener('change', (e) => {
    const input = e.target as HTMLInputElement
    setServerUrl(input.value)
  })

  document.querySelectorAll('.auth-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.getAttribute('data-tab')
      document.querySelectorAll('.auth-tab').forEach(t => {
        t.classList.remove('active')
        t.setAttribute('aria-selected', 'false')
      })
      tab.classList.add('active')
      tab.setAttribute('aria-selected', 'true')
      clearAuthBanner()

      if (tabName === 'login') {
        document.getElementById('login-form')!.style.display = 'flex'
        document.getElementById('register-form')!.style.display = 'none'
      } else {
        document.getElementById('login-form')!.style.display = 'none'
        document.getElementById('register-form')!.style.display = 'flex'
      }
    })
  })

  document.getElementById('login-btn')?.addEventListener('click', async () => {
    clearAuthBanner()
    const username = (document.getElementById('username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('password') as HTMLInputElement).value

    if (!username || !password) {
      const msg = '请输入用户名和密码'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
      return
    }

    const btn = document.getElementById('login-btn') as HTMLButtonElement
    const idleLabel = '登录'
    btn.disabled = true
    btn.textContent = '登录中…'
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/login`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password }
      })
      const data = toRecord(resp.data)
      const token = (data.access_token as string | undefined) || (resp.data as { access_token?: string })?.access_token

      if (resp.status === 200 && token) {
        setToken(token)
        showToast('登录成功', 'ok')
        await renderHome()
        return
      }
      const msg = extractApiErrorMessage(data) || '登录失败'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
    } catch (err) {
      const msg = '登录失败：' + (err instanceof Error ? err.message : String(err))
      showAuthBanner('err', msg)
      showToast(msg, 'err')
    } finally {
      btn.disabled = false
      btn.textContent = idleLabel
    }
  })

  document.getElementById('register-btn')?.addEventListener('click', async () => {
    clearAuthBanner()
    const username = (document.getElementById('reg-username') as HTMLInputElement).value.trim()
    const password = (document.getElementById('reg-password') as HTMLInputElement).value
    const password2 = (document.getElementById('reg-password2') as HTMLInputElement).value
    const inviteCode = (document.getElementById('invite-code') as HTMLInputElement).value.trim()

    if (!username || !password) {
      const msg = '请输入用户名和密码'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
      return
    }
    if (password !== password2) {
      const msg = '两次密码不一致'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
      return
    }
    if (!inviteCode) {
      const msg = '请输入邀请码'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
      return
    }

    const btn = document.getElementById('register-btn') as HTMLButtonElement
    const idleLabel = '注册'
    btn.disabled = true
    btn.textContent = '注册中…'
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/auth/register`,
        headers: { 'Content-Type': 'application/json' },
        data: { username, password, invite_code: inviteCode }
      })
      const data = toRecord(resp.data)
      const token = (data.access_token as string | undefined) || (resp.data as { access_token?: string })?.access_token

      if (resp.status === 200 && token) {
        setToken(token)
        showToast('注册成功', 'ok')
        await renderHome()
        return
      }
      const msg = extractApiErrorMessage(data) || '注册失败'
      showAuthBanner('err', msg)
      showToast(msg, 'err')
    } catch (err) {
      const msg = '注册失败：' + (err instanceof Error ? err.message : String(err))
      showAuthBanner('err', msg)
      showToast(msg, 'err')
    } finally {
      btn.disabled = false
      btn.textContent = idleLabel
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
        <button type="button" class="action-btn primary" id="global-refresh">🔄 刷新</button>
        <button type="button" class="action-btn secondary" id="global-settings">⚙️ 设置</button>
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

  document.getElementById('global-refresh')?.addEventListener('click', () => {
    void loadServices({ userRefresh: true })
  })
  document.getElementById('global-settings')?.addEventListener('click', showServiceSelector)

  void loadServices()
}

function formatRefreshClock(d: Date): string {
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

type LoadServicesOptions = { userRefresh?: boolean }

// 加载服务数据
async function loadServices(opts?: LoadServicesOptions) {
  const userRefresh = !!opts?.userRefresh
  const cardsEl = document.getElementById('cards')
  if (!cardsEl) return

  const refreshBtn = document.getElementById('global-refresh') as HTMLButtonElement | null
  if (userRefresh && refreshBtn) {
    refreshBtn.disabled = true
    refreshBtn.textContent = '刷新中…'
  }

  const serverUrl = getServerUrl()
  const token = getToken()

  try {
    const registry = await fetchServiceRegistry(serverUrl, token)
    cachedServiceRegistry = registry

    const results = await Promise.all(
      registry.map(async (service) => {
        try {
          const resp = await CapacitorHttp.request({
            method: 'GET',
            url: `${serverUrl}/api/${encodeURIComponent(service.id)}/`,
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`
            }
          })
          const data = toRecord(resp.data)
          return { service, resp, data, fetchError: null as string | null }
        } catch (err) {
          return {
            service,
            resp: null,
            data: {} as Record<string, unknown>,
            fetchError: err instanceof Error ? err.message : String(err)
          }
        }
      })
    )

    const cards: string[] = []
    let okCount = 0
    let failCount = 0

    for (const { service, resp, data, fetchError } of results) {
      const title = serviceCardTitle(service)
      if (fetchError) {
        failCount++
        cards.push(createErrorCard(service.id, title, fetchError))
        continue
      }
      const status = resp?.status ?? 0
      const detailMsg = extractApiErrorMessage(data)
      const legacyErr = data.error != null ? String(data.error) : ''
      const ok = status === 200 && !legacyErr
      if (ok) {
        okCount++
        const { stats, percentStr } = buildMobileCardStats(service, data)
        cards.push(createCard(service.id, title, 'ok', '正常', stats, percentStr))
      } else {
        failCount++
        const errorMsg = detailMsg || legacyErr || '请设置 Cookie'
        cards.push(createErrorCard(service.id, title, errorMsg))
      }
    }

    cardsEl.innerHTML = cards.join('')

    const now = new Date()
    const clock = formatRefreshClock(now)
    const total = okCount + failCount

    if (userRefresh) {
      if (total === 0) {
        showToast(`已刷新 · ${clock} · 暂无可用服务`, 'info')
      } else if (failCount === 0) {
        showToast(`刷新成功 · ${clock}`, 'ok')
      } else if (okCount === 0) {
        showToast(`刷新完成但未取到可用数据（${failCount} 项需配置或网络失败）`, 'err')
      } else {
        showToast(`已刷新：${okCount} 项正常，${failCount} 项异常或待配置 · ${clock}`, 'info')
      }
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    if (userRefresh) showToast('刷新失败：' + errorMsg, 'err')

    cardsEl.innerHTML = `
      <div class="error">
        <p>连接失败</p>
        <p class="detail">${errorMsg}</p>
        <button type="button" id="retry-btn" class="action-btn primary">重试</button>
      </div>
    `
    document.getElementById('retry-btn')?.addEventListener('click', () => {
      void loadServices({ userRefresh: true })
    })
  } finally {
    if (userRefresh && refreshBtn) {
      refreshBtn.disabled = false
      refreshBtn.textContent = '🔄 刷新'
    }
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
      { sid: 'minimax', metric: 'percent' },
      { sid: 'xfyun', metric: 'percent' }
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

function normalizeServiceId(id: string | null | undefined): string | null {
  const k = String(id || '')
    .trim()
    .toLowerCase()
  if (!k) return null
  const regHit = cachedServiceRegistry.find(s => s.id.toLowerCase() === k)
  if (regHit) return regHit.id
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
  const service = getServiceUiMeta(sid)
  const reg =
    cachedServiceRegistry.find(s => s.id === sid) ?? FALLBACK_SERVICE_REGISTRY.find(s => s.id === sid)
  const showGroupIdBlock =
    reg?.capabilities && typeof reg.capabilities.requires_group_id === 'boolean'
      ? reg.capabilities.requires_group_id
      : sid === 'minimax'
  const groupIdPanelClass = showGroupIdBlock
    ? 'group-id-input group-id-panel group-id-panel--minimax'
    : 'group-id-input group-id-panel group-id-panel--hidden'

  app.innerHTML = `
    <div class="container">
      <header>
        <button class="back-btn" id="back-btn">← 返回</button>
        <h1>${serviceHeadingHtml(service.icon, service.name)}</h1>
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
  const defaultAccountName = `我的${service.name}账号`

  function askRequiredAccountName(initialName = defaultAccountName): string | null {
    const input = window.prompt('请输入配置名称（必填，1-20 字符）', initialName)
    if (input === null) return null
    const nextName = input.trim()
    if (!nextName) {
      showToast('配置名称不能为空', 'err')
      return ''
    }
    if (nextName.length > 20) {
      showToast('配置名称长度需为 1-20 个字符', 'err')
      return ''
    }
    if (!/^[\u4e00-\u9fffA-Za-z0-9_-]+$/.test(nextName)) {
      showToast('配置名称仅支持中文、英文、数字、下划线和横线', 'err')
      return ''
    }
    return nextName
  }

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

      if (showGroupIdBlock) {
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

      if (showGroupIdBlock) {
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

      const accountName = askRequiredAccountName()
      if (accountName === null) return
      if (!accountName) return

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
          name: accountName,
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

    if (showGroupIdBlock) {
      if (!cookie || !gidInput) {
        showToast('手动 Cookie 与 GroupId 须同时填写后再保存', 'err')
        return
      }
    } else if (!cookie) {
      showToast('请输入 Cookie', 'err')
      return
    }

    const accountName = askRequiredAccountName()
    if (accountName === null) return
    if (!accountName) return
    
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
          name: accountName,
          cookies: cookie,
          group_id: showGroupIdBlock ? gidInput : null
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
  const list = cachedServiceRegistry.length > 0 ? cachedServiceRegistry : FALLBACK_SERVICE_REGISTRY
  const serviceButtons = list
    .map((s) => {
      const iconRaw = s.icon != null && String(s.icon).trim() !== '' ? String(s.icon).trim() : ''
      const iconInner = iconRaw ? serviceIconHtml(iconRaw) : ''
      const rawName = s.name || s.id
      const safeName = rawName.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      const safeId = String(s.id).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
      return `
        <button class="service-item" data-service="${safeId}">
          <span class="service-icon">${iconInner}</span>
          <span class="service-name">${safeName}</span>
        </button>`
    })
    .join('')

  app.innerHTML = `
    <div class="container">
      <header>
        <button class="back-btn" id="back-btn">← 返回</button>
        <h1>⚙️ Cookie 设置</h1>
        <p class="subtitle">选择要配置的服务</p>
      </header>
      
      <div class="service-list">
        ${serviceButtons}
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
  const pctNum = Number(percent)
  const pctLabel = Number.isFinite(pctNum) ? pctNum.toFixed(1) : String(percent)
  const widthPct = Number.isFinite(pctNum) ? Math.max(0, Math.min(100, pctNum)) : 0
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
        <div class="card-progress-wrap">
          <div class="progress-row">
            <div class="progress-bar" role="progressbar" aria-valuenow="${Math.round(widthPct)}" aria-valuemin="0" aria-valuemax="100">
              <div class="progress-fill ${colorClass}" style="width: ${widthPct}%"></div>
            </div>
            <span class="progress-pct" aria-hidden="true">${pctLabel}%</span>
          </div>
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

async function startApp(): Promise<void> {
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

const WELCOME_AUTO_ENTER_SEC = 5

function renderWelcome(): void {
  let welcomeTimer: ReturnType<typeof setInterval> | null = null
  let welcomeLeft = WELCOME_AUTO_ENTER_SEC
  let welcomeDone = false

  const leaveWelcome = (): void => {
    if (welcomeDone) return
    welcomeDone = true
    if (welcomeTimer !== null) {
      clearInterval(welcomeTimer)
      welcomeTimer = null
    }
    void startApp()
  }

  app.innerHTML = `
    <div class="welcome-screen">
      <div class="welcome-countdown-wrap" style="--welcome-sec:${WELCOME_AUTO_ENTER_SEC}" aria-live="polite" aria-atomic="true">
        <svg class="welcome-countdown-ring" viewBox="0 0 40 40" aria-hidden="true">
          <defs>
            <linearGradient id="wcRingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="#c084fc"/>
              <stop offset="45%" stop-color="#6366f1"/>
              <stop offset="100%" stop-color="#22d3ee"/>
            </linearGradient>
          </defs>
          <circle class="welcome-countdown-ring-track" cx="20" cy="20" r="17" pathLength="100"/>
          <circle class="welcome-countdown-ring-progress" cx="20" cy="20" r="17" pathLength="100"/>
        </svg>
        <div class="welcome-countdown-inner">
          <span class="welcome-countdown-num" id="welcome-countdown">${WELCOME_AUTO_ENTER_SEC}</span>
          <span class="welcome-countdown-unit">s</span>
        </div>
      </div>
      <div class="welcome-inner">
        <div class="welcome-brand">
          <div class="welcome-logo-wrap">
            <div class="welcome-logo-frame">
              <img class="welcome-logo-img" src="/welcome-logo.png" width="96" height="96" alt="" decoding="async" />
            </div>
          </div>
          <h1 class="welcome-title">Token Monitor</h1>
          <p class="welcome-tagline">API Quota Monitoring</p>
        </div>
        <ul class="welcome-features" aria-label="功能介绍">
          <li class="welcome-card">
            <span class="welcome-card-icon" aria-hidden="true">
              <svg class="welcome-feature-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="wfg1" x1="2" y1="20" x2="22" y2="4" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#c084fc"/><stop offset="0.55" stop-color="#6366f1"/><stop offset="1" stop-color="#22d3ee"/>
                  </linearGradient>
                </defs>
                <path d="M3 17.5V6.5L7 11l3.5-5L14 10l4-6.5v14" stroke="url(#wfg1)" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>
                <circle cx="3" cy="17.5" r="1.35" fill="url(#wfg1)"/>
                <circle cx="7" cy="11" r="1.35" fill="url(#wfg1)"/>
                <circle cx="10.5" cy="6" r="1.35" fill="url(#wfg1)"/>
                <circle cx="14" cy="10" r="1.35" fill="url(#wfg1)"/>
                <circle cx="18" cy="3.5" r="1.35" fill="url(#wfg1)"/>
              </svg>
            </span>
            <div class="welcome-card-text">
              <h2>实时监控</h2>
              <p>实时追踪 API 用量，图形化展示统计数据。</p>
            </div>
          </li>
          <li class="welcome-card">
            <span class="welcome-card-icon" aria-hidden="true">
              <svg class="welcome-feature-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="wfg2" x1="4" y1="3" x2="20" y2="21" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#a855f7"/><stop offset="0.5" stop-color="#6366f1"/><stop offset="1" stop-color="#38bdf8"/>
                  </linearGradient>
                </defs>
                <path d="M12 22a2.5 2.5 0 002.45-2H9.55A2.5 2.5 0 0012 22z" fill="url(#wfg2)" opacity="0.9"/>
                <path d="M18 8a6 6 0 10-12 0c0 6.5-2.5 7.5-2.5 7.5h17S18 14.5 18 8z" stroke="url(#wfg2)" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </span>
            <div class="welcome-card-text">
              <h2>智能告警</h2>
              <p>设置额度阈值，当用量接近上限时接收及时提醒。</p>
            </div>
          </li>
          <li class="welcome-card">
            <span class="welcome-card-icon" aria-hidden="true">
              <svg class="welcome-feature-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="wfg3" x1="4" y1="21" x2="20" y2="4" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#c084fc"/><stop offset="0.6" stop-color="#4f46e5"/><stop offset="1" stop-color="#22d3ee"/>
                  </linearGradient>
                </defs>
                <path d="M12 21.5S5 18.5 5 10.5V6l7-3 7 3v4.5c0 8-7 11-7 11z" stroke="url(#wfg3)" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M12 11.5v4M10 13.5h4" stroke="url(#wfg3)" stroke-width="1.4" stroke-linecap="round"/>
              </svg>
            </span>
            <div class="welcome-card-text">
              <h2>安全存储</h2>
              <p>安全存储和管理您的 API 密钥，保障数据安全。</p>
            </div>
          </li>
        </ul>
        <button type="button" class="welcome-cta" id="welcome-continue">开始使用</button>
      </div>
    </div>
  `

  const cdEl = document.getElementById('welcome-countdown')

  welcomeTimer = window.setInterval(() => {
    welcomeLeft -= 1
    if (welcomeLeft <= 0) {
      leaveWelcome()
      return
    }
    if (cdEl) cdEl.textContent = String(welcomeLeft)
  }, 1000)

  document.getElementById('welcome-continue')?.addEventListener('click', () => {
    leaveWelcome()
  })
}

/** 未登录才显示欢迎页；已登录且 token 有效则直进首页 */
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
  renderWelcome()
}

bootstrap()
