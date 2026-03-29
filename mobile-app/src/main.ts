// Token Monitor Mobile App
// 爱丽丝的作品 ✨

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
const WebViewPlugin = Capacitor.registerPlugin('WebViewPlugin')

// 获取保存的服务器地址
function getServerUrl(): string {
  return localStorage.getItem('serverUrl') || DEFAULT_SERVER
}

// 保存服务器地址
function setServerUrl(url: string): void {
  localStorage.setItem('serverUrl', url)
}

// 主页面
function renderHome() {
  const serverUrl = getServerUrl()
  
  app.innerHTML = `
    <div class="container">
      <header>
        <h1>✨ Token Monitor</h1>
        <p class="subtitle">API额度实时监控</p>
      </header>
      
      <div class="server-config">
        <label>服务器地址</label>
        <input type="text" id="server-input" value="${serverUrl}" placeholder="http://192.168.3.36:5188">
        <button id="save-server">保存</button>
      </div>
      
      <div class="action-bar">
        <button class="action-btn primary" id="global-refresh">🔄 刷新</button>
        <button class="action-btn secondary" id="global-settings">⚙️ 设置</button>
      </div>
      
      <div class="cards" id="cards">
        <div class="loading">正在加载...</div>
      </div>
    </div>
  `
  
  document.getElementById('save-server')?.addEventListener('click', () => {
    const input = document.getElementById('server-input') as HTMLInputElement
    if (input && input.value) {
      setServerUrl(input.value)
      loadServices()
    }
  })
  
  loadServices()
}

// 加载服务数据
async function loadServices() {
  const cardsEl = document.getElementById('cards')
  if (!cardsEl) return
  
  const serverUrl = getServerUrl()
  
  try {
    const [minimaxResp, xfyunResp] = await Promise.all([
      CapacitorHttp.request({
        method: 'GET',
        url: `${serverUrl}/api/minimax`,
        headers: { 'Content-Type': 'application/json' }
      }),
      CapacitorHttp.request({
        method: 'GET',
        url: `${serverUrl}/api/xfyun`,
        headers: { 'Content-Type': 'application/json' }
      })
    ])
    
    const cards: string[] = []
    
    // MiniMax 卡片 - 使用 page_info 格式
    if (minimaxResp.status === 200 && minimaxResp.data && !minimaxResp.data.error) {
      const pageInfo = minimaxResp.data.page_info || {}
      const used = pageInfo.used ?? '-'
      const total = pageInfo.total ?? '-'
      const percent = pageInfo.percent ?? 0
      const expiresAt = pageInfo.expiresAt || '-'
      const resetHours = pageInfo.resetHours || 0
      const resetMinutes = pageInfo.resetMinutes || 0
      
      const resetTime = resetHours > 0 
        ? `${resetHours}小时${resetMinutes}分钟` 
        : `${resetMinutes}分钟`
      
      cards.push(createCard('minimax', '🍊 MiniMax', 'ok', '正常', [
        { label: '使用量', value: `${used}/${total} (${percent}%)` },
        { label: '截止日期', value: expiresAt },
        { label: '重置时间', value: resetTime }
      ], String(percent), true))
    } else {
      cards.push(createErrorCard('minimax', '🍊 MiniMax', minimaxResp.data?.error || '请登录'))
    }
    
    // 讯飞卡片 - 使用 page_info 格式
    if (xfyunResp.status === 200 && xfyunResp.data && !xfyunResp.data.error) {
      const pageInfo = xfyunResp.data.page_info || {}
      const dailyQuota = pageInfo.dailyQuota ? `${pageInfo.dailyQuota} 万` : '-'
      const dailyUsed = pageInfo.dailyUsed ? `${pageInfo.dailyUsed} 万` : '-'
      const dailyRemain = pageInfo.dailyRemain ? `${pageInfo.dailyRemain} 万` : '-'
      const expiresAt = pageInfo.expiresAt || '-'
      
      // 计算使用率
      const percent = pageInfo.dailyQuota > 0 
        ? ((pageInfo.dailyUsed / pageInfo.dailyQuota) * 100).toFixed(1) 
        : '0'
      
      cards.push(createCard('xfyun', '🔵 讯飞星辰 MaaS', 'ok', '正常', [
        { label: '每日额度', value: dailyQuota },
        { label: '今日已用', value: dailyUsed },
        { label: '今日剩余', value: dailyRemain },
        { label: '到期时间', value: expiresAt }
      ], percent, true))
    } else {
      cards.push(createErrorCard('xfyun', '🔵 讯飞星辰 MaaS', xfyunResp.data?.error || '请登录'))
    }
    
    cardsEl.innerHTML = cards.join('')
    
    // 绑定全局刷新按钮事件
    document.getElementById('global-refresh')?.addEventListener('click', loadServices)
    
    // 绑定全局设置按钮事件 - 显示服务选择
    document.getElementById('global-settings')?.addEventListener('click', () => {
      showServiceSelector()
    })
    
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    cardsEl.innerHTML = `
      <div class="error">
        <p>连接失败</p>
        <p class="detail">${errorMsg}</p>
        <button id="retry-btn">重试</button>
      </div>
    `
    document.getElementById('retry-btn')?.addEventListener('click', loadServices)
  }
}

// Cookie 设置页
function renderCookiePage(serviceId: string) {
  const service = SERVICES[serviceId as keyof typeof SERVICES]
  if (!service) return
  
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
            <li>点击「打开登录页」按钮</li>
            <li>在页面中完成登录</li>
            <li>登录成功后点击「提取数据」</li>
            <li>点击「保存」保存数据</li>
          </ol>
        </div>
        
        <button class="action-btn primary" id="open-login">
          🌐 打开登录页
        </button>
        
        <button class="action-btn secondary" id="extract-cookie">
          📋 提取数据
        </button>
        
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
        cookieDomains: service.cookieDomains
      })
    } catch (err) {
      console.error('打开登录页失败', err)
    }
  })
  
  document.getElementById('extract-cookie')?.addEventListener('click', async () => {
    try {
      const result = await WebViewPlugin.getExtractedCookies()
      const cookies = result.cookies as string
      const pageDataStr = result.pageData as string || '{}'
      
      let pageData: any = {}
      try {
        pageData = JSON.parse(pageDataStr)
        currentPageData = pageData
      } catch (e) {}
      
      if (cookies && cookies.length > 0) {
        const displayEl = document.getElementById('cookie-display')
        const textareaEl = document.getElementById('cookie-text') as HTMLTextAreaElement
        if (displayEl && textareaEl) {
          displayEl.style.display = 'block'
          textareaEl.value = cookies
        }
        
        const infoEl = document.getElementById('page-info')
        if (infoEl && Object.keys(pageData).length > 0) {
          let infoHtml = '<div class="page-info">'
          if (pageData.expiresAt) infoHtml += `<p>📅 截止日期: ${pageData.expiresAt}</p>`
          if (pageData.resetMinutes) infoHtml += `<p>⏰ 重置时间: ${pageData.resetMinutes} 分钟后</p>`
          if (pageData.resetHours) infoHtml += `<p>⏰ 重置时间: ${pageData.resetHours} 小时后</p>`
          if (pageData.used && pageData.total) infoHtml += `<p>📊 使用量: ${pageData.used}/${pageData.total}</p>`
          infoHtml += '</div>'
          infoEl.innerHTML = infoHtml
        }
        
        alert('成功提取数据！')
      } else {
        alert('未找到数据，请确保已在登录页完成登录并点击了「提取数据」按钮')
      }
    } catch (err) {
      alert('提取失败：' + (err instanceof Error ? err.message : String(err)))
    }
  })
  
  document.getElementById('save-cookie')?.addEventListener('click', async () => {
    const textarea = document.getElementById('cookie-text') as HTMLTextAreaElement
    const cookie = textarea.value.trim()
    if (!cookie) {
      alert('没有 Cookie 可保存')
      return
    }
    
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/api/set-cookie`,
        headers: { 'Content-Type': 'application/json' },
        data: { service: serviceId, cookies: cookie, page_info: currentPageData }
      })
      
      if (resp.status === 200 && resp.data.success) {
        alert('保存成功！')
        await WebViewPlugin.clearExtractedCookies()
        renderHome()
      } else {
        alert('保存失败：' + (resp.data.error || '未知错误'))
      }
    } catch (err) {
      alert('保存失败：' + (err instanceof Error ? err.message : String(err)))
    }
  })
  
  document.getElementById('save-manual')?.addEventListener('click', async () => {
    const textarea = document.getElementById('manual-cookie') as HTMLTextAreaElement
    const cookie = textarea.value.trim()
    if (!cookie) {
      alert('请输入 Cookie')
      return
    }
    
    try {
      const resp = await CapacitorHttp.request({
        method: 'POST',
        url: `${getServerUrl()}/api/set-cookie`,
        headers: { 'Content-Type': 'application/json' },
        data: { service: serviceId, cookies: cookie }
      })
      
      if (resp.status === 200 && resp.data.success) {
        alert('保存成功！')
        renderHome()
      } else {
        alert('保存失败：' + (resp.data.error || '未知错误'))
      }
    } catch (err) {
      alert('保存失败：' + (err instanceof Error ? err.message : String(err)))
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
function createCard(serviceId: string, title: string, badgeClass: string, badgeText: string, stats: {label: string, value: string}[], percent: string, showButtons: boolean = false) {
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
        <span class="badge error">需登录</span>
      </div>
      <div class="card-body">
        <p class="error-msg">${errorMsg}</p>
      </div>
    </div>
  `
}

// 启动
renderHome()
