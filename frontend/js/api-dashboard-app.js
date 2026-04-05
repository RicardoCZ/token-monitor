/**
 * 监控看板 — 鉴权、注册表同步、卡片渲染、刷新（api.html）
 *
 * 依赖：依次加载 api-dashboard-state.js、api-dashboard-core.js 后再加载本文件。
 * 全局：向 window 暴露 refreshAll、logout、closeModal、showLoginModal（供 HTML onclick 等使用）。
 */
(function (w) {
    const S = w.TMD;
    const U = w.TMDCore;

    const App = {
        buildTopNavLinks(isAdmin) {
            const Ui = w.TMDUi;
            if (!Ui || typeof Ui.buildTopNavLinks !== "function") {
                console.warn("[api-dashboard-app] 请先加载 js/ui-shared.js（TMDUi.buildTopNavLinks）");
                return "";
            }
            return Ui.buildTopNavLinks(S.CURRENT_PAGE, { showAdminLink: !!isAdmin });
        },

        _refreshFeedbackClearTimer: null,

        setRefreshFeedback(text, isError = false) {
            const el = document.getElementById("refresh-feedback");
            if (!el) return;
            el.textContent = text || "";
            el.className = "refresh-feedback" + (isError ? " error" : "");
        },

        /** 成功提示（如「刷新完成」）在若干秒后自动清空；错误文案保留至下次刷新 */
        scheduleRefreshFeedbackAutoClear(delayMs = 2300) {
            if (this._refreshFeedbackClearTimer != null) {
                clearTimeout(this._refreshFeedbackClearTimer);
                this._refreshFeedbackClearTimer = null;
            }
            this._refreshFeedbackClearTimer = setTimeout(() => {
                this._refreshFeedbackClearTimer = null;
                const el = document.getElementById("refresh-feedback");
                if (!el || el.classList.contains("error")) return;
                el.textContent = "";
            }, delayMs);
        },

        cancelRefreshFeedbackAutoClear() {
            if (this._refreshFeedbackClearTimer != null) {
                clearTimeout(this._refreshFeedbackClearTimer);
                this._refreshFeedbackClearTimer = null;
            }
        },

        updateLastUpdateText(timestamp, suffix = "") {
            const el = document.getElementById("last-update");
            if (!el) return;
            const dt = new Date(Number(timestamp) || Date.now());
            el.textContent = `最后更新: ${dt.toLocaleTimeString("zh-CN")}${suffix}`;
        },

        async checkAuth() {
            const userInfo = document.getElementById("user-info");

            if (!S.authToken) {
                w.location.href = "login.html";
                return false;
            }

            try {
                const resp = await fetch(`${S.API_BASE}/auth/me`, {
                    headers: { Authorization: `Bearer ${S.authToken}` },
                });

                if (resp.ok) {
                    S.currentUser = await resp.json();

                    userInfo.innerHTML = `
                        <span>👤 ${U.escapeHtml(S.currentUser.username)}</span>
                        ${this.buildTopNavLinks(S.currentUser.role === "admin")}
                        <span class="header-top-link" style="cursor: pointer;" role="button" tabindex="0"
                              onclick="logout()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();logout();}">退出</span>
                    `;
                    return true;
                }
                localStorage.removeItem("token");
                localStorage.removeItem("user");
                w.location.href = "login.html";
                return false;
            } catch (e) {
                console.error("Auth check failed:", e);
                return false;
            }
        },

        logout() {
            localStorage.removeItem("token");
            localStorage.removeItem("user");
            sessionStorage.removeItem(S.DASHBOARD_CACHE_KEY);
            w.location.href = "login.html";
        },

        renderServiceCardsSkeleton() {
            const container = document.getElementById("services-cards");
            if (!container) return;
            if (!S.serviceRegistry.length) {
                container.innerHTML = `
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">暂无可用服务</span>
                            <span class="card-badge badge-warn">空</span>
                        </div>
                        <div class="service-card-content">
                            <div class="loading">服务注册表为空</div>
                        </div>
                    </div>
                `;
                return;
            }

            container.innerHTML = S.serviceRegistry.map(service => `
                <div class="card" id="service-card-${U.escapeHtml(service.id)}">
                    <div class="card-header">
                        <span class="card-title">${U.renderServiceIconHtml(service.icon || "🧩")}<span class="card-title-text">${U.escapeHtml(service.name || service.id)}</span></span>
                        <span class="card-badge badge-ok" id="service-badge-${U.escapeHtml(service.id)}">加载中</span>
                    </div>
                    <div class="service-card-content" id="service-content-${U.escapeHtml(service.id)}">
                        <div class="card-dynamic">
                            <div class="loading">正在查询 ${U.escapeHtml(service.name || service.id)} 额度</div>
                        </div>
                        <div class="card-sparkline">
                            <div class="card-sparkline-head">
                                <span class="card-sparkline-title">最近 7 天 · 使用率</span>
                            </div>
                            <div class="card-sparkline-chart" id="service-sparkline-chart-${U.escapeHtml(service.id)}">
                                <span class="sparkline-loading">加载中…</span>
                            </div>
                        </div>
                    </div>
                </div>
            `).join("");
        },

        renderServiceCardError(badge, content, message) {
            const msg = message || "加载失败";
            let badgeClass, badgeText;
            if (/解密失败|Decrypt/i.test(msg)) {
                badgeClass = "card-badge badge-error";
                badgeText = "错误";
            } else if (/请先设置|未配置 Cookie|Cookie 未配置|NO_COOKIE/i.test(msg)) {
                badgeClass = "card-badge badge-warn";
                badgeText = "未配置";
            } else {
                badgeClass = "card-badge badge-error";
                badgeText = "需登录";
            }
            badge.className = badgeClass;
            badge.textContent = badgeText;
            content.innerHTML = `
                <div class="login-box">
                    <p style="color: #888; font-size: 13px;">${msg}</p>
                    <p style="color: #666; font-size: 12px; margin-top: 10px;">请使用页面顶部「🔧 设置凭证」进行配置。</p>
                </div>
            `;
        },

        buildCardDynamicInnerHtml(service, data) {
            const { rows, usage } = U.buildMetricRows(service, data);
            const percent = U.getNumberValue(usage.percent);
            const colorClass = percent > 80 ? "red" : percent > 50 ? "orange" : "green";

            const resetValue =
                usage.resetCaption ||
                (service.id === "xfyun" ? "每日 00:00" : "") ||
                U.formatResetTime(usage.resetHours, usage.resetMinutes);
            const metaRows = [
                { label: "到期时间", value: usage.expiresAt || "-" },
                { label: "重置时间", value: resetValue },
            ];

            const hasMeta = metaRows.length > 0;
            const statsCells = rows
                .map((row, i) => {
                    const beforeMeta = hasMeta && i === rows.length - 1;
                    const bm = beforeMeta ? " metric-before-meta" : "";
                    return `
                        <span class="stat-label${bm}">${U.escapeHtml(row.label)}</span>
                        <span class="stat-value${bm}">${U.escapeHtml(row.value)}</span>
                    `;
                })
                .join("");
            const metaCells = metaRows
                .map((row, idx) => {
                    const st = idx === 0 ? " metric-meta-start" : "";
                    return `
                        <span class="stat-label${st}">${U.escapeHtml(row.label)}</span>
                        <span class="stat-value${st}">${U.escapeHtml(row.value)}</span>
                    `;
                })
                .join("");

            return `
                <div class="metric-sheet" role="group" aria-label="用量与到期信息">
                    ${statsCells}
                    ${metaCells}
                </div>
                <div class="card-progress-wrap">
                    <div class="progress-row">
                        <div class="progress-bar" role="progressbar" aria-valuenow="${Math.round(percent)}" aria-valuemin="0" aria-valuemax="100">
                            <div class="progress-fill ${colorClass}" style="width: ${Math.max(0, Math.min(100, percent))}%"></div>
                        </div>
                        <span class="progress-pct" aria-hidden="true">${percent.toFixed(1)}%</span>
                    </div>
                </div>
            `;
        },

        renderServiceCardSuccess(service, data) {
            const badge = document.getElementById(`service-badge-${service.id}`);
            const content = document.getElementById(`service-content-${service.id}`);
            if (!badge || !content) return;
            badge.className = "card-badge badge-ok";
            badge.textContent = "正常";

            const dynamicHtml = this.buildCardDynamicInnerHtml(service, data);
            const dynamicEl = content.querySelector(".card-dynamic");
            const sparkChart = document.getElementById(`service-sparkline-chart-${service.id}`);

            if (dynamicEl && sparkChart) {
                dynamicEl.innerHTML = dynamicHtml;
                void this.loadCardSparkline(service, { soft: true });
                return;
            }

            content.innerHTML = `
                <div class="card-dynamic">${dynamicHtml}</div>
                <div class="card-sparkline">
                    <div class="card-sparkline-head">
                        <span class="card-sparkline-title">最近 7 天 · 使用率</span>
                    </div>
                    <div class="card-sparkline-chart" id="service-sparkline-chart-${U.escapeHtml(service.id)}">
                        <span class="sparkline-loading">加载中…</span>
                    </div>
                </div>
            `;
            void this.loadCardSparkline(service);
        },

        renderFromCachedDashboard() {
            const cache = U.loadDashboardCache();
            if (!cache) return false;
            S.serviceRegistry = cache.registry;
            S.serviceDataCache = cache.dataByService || {};
            this.renderServiceCardsSkeleton();
            for (const service of S.serviceRegistry) {
                const cachedData = S.serviceDataCache[service.id];
                if (!cachedData) continue;
                this.renderServiceCardSuccess(service, cachedData);
            }
            this.updateLastUpdateText(cache.updatedAt || Date.now(), "（缓存）");
            this.setRefreshFeedback("已显示缓存数据，正在刷新最新数据...");
            void this.syncAccountIdByService().then(() => {
                for (const service of S.serviceRegistry) {
                    if (S.serviceDataCache[service.id]) {
                        void this.loadCardSparkline(service);
                    }
                }
            });
            void this.loadRecentAlertsSummary();
            return true;
        },

        async syncAccountIdByService() {
            S.serviceAccountIds = {};
            try {
                const resp = await fetch(`${S.API_BASE}/api/accounts?_=${Date.now()}`, {
                    headers: { Authorization: `Bearer ${S.authToken}` },
                });
                const data = await resp.json();
                if (!resp.ok) return;
                const arr = Array.isArray(data) ? data : [];
                for (const a of arr) {
                    const sid = String(a.service_id || "").trim();
                    if (sid && a.id != null) {
                        S.serviceAccountIds[sid] = a.id;
                    }
                }
            } catch (e) {
                /* ignore */
            }
        },

        async fetchPercentHistoryForAccount(accountId) {
            const endMs = Date.now();
            const startIso = new Date(endMs - 7 * 24 * 60 * 60 * 1000).toISOString();
            const endIso = new Date(endMs).toISOString();
            /* 与历史趋势页一致：后端 limit 上限 100，需分页拉满窗口内 percent 快照 */
            const limit = 100;
            const MAX_FETCH_PAGES = 40;
            const MAX_POINTS = 3000;
            const all = [];
            let offset = 0;
            const bust = Date.now();
            for (let i = 0; i < MAX_FETCH_PAGES && all.length < MAX_POINTS; i += 1) {
                const url =
                    `${S.API_BASE}/api/accounts/${accountId}/history?limit=${limit}&offset=${offset}` +
                    `&start_at=${encodeURIComponent(startIso)}&end_at=${encodeURIComponent(endIso)}` +
                    `&metric_key=${encodeURIComponent("percent")}&_=${bust}&p=${i}`;
                const resp = await fetch(url, {
                    headers: { Authorization: `Bearer ${S.authToken}` },
                });
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(U.extractApiErrorMessage(data));
                }
                const items = Array.isArray(data.items) ? data.items : [];
                all.push(...items);
                if (!data.pagination?.has_more || !items.length) break;
                offset += limit;
            }
            const sorted = all
                .filter((it) => it && it.collected_at != null && it.percent != null)
                .sort((a, b) => new Date(a.collected_at).getTime() - new Date(b.collected_at).getTime());
            return sorted.map((it) => U.getNumberValue(it.percent));
        },

        async loadCardSparkline(service, options = {}) {
            const chartEl = document.getElementById(`service-sparkline-chart-${service.id}`);
            if (!chartEl) return;
            const accountId = S.serviceAccountIds[service.id];
            if (!accountId) {
                chartEl.innerHTML = '<span class="sparkline-empty">暂无绑定账号</span>';
                return;
            }
            const soft = options.soft === true;
            const keepVisual = soft && !!chartEl.querySelector(".sparkline-svg");
            if (!keepVisual) {
                chartEl.innerHTML = '<span class="sparkline-loading">加载中…</span>';
            }
            try {
                const series = await this.fetchPercentHistoryForAccount(accountId);
                const strokePalette = {
                    minimax: "#e8a87c",
                    xfyun: "#6f88ff",
                };
                const stroke = strokePalette[service.id] ?? "#8fa3e6";
                chartEl.innerHTML = U.buildSparklineSvg(series, stroke);
            } catch (e) {
                if (!keepVisual) {
                    chartEl.innerHTML = '<span class="sparkline-empty">趋势加载失败</span>';
                }
            }
        },

        resolveDashboardUserId() {
            const u = S.currentUser;
            if (u && u.id != null && Number.isFinite(Number(u.id))) {
                return Number(u.id);
            }
            try {
                const raw = localStorage.getItem("user");
                if (!raw) return null;
                const parsed = JSON.parse(raw);
                const id = Number(parsed && parsed.id);
                return Number.isFinite(id) ? id : null;
            } catch (e) {
                return null;
            }
        },

        _recentAlertsStepTimer: null,
        _recentAlertsScrollRaf: null,
        _recentAlertsListEl: null,
        _recentAlertsBound: null,
        _recentAlertsPaused: false,
        /** 丢弃过期的并发「最近告警」请求结果，避免后返回的旧列表盖住新数据 */
        _recentAlertsLoadGen: 0,

        stopRecentAlertsTicker() {
            if (this._recentAlertsStepTimer != null) {
                clearTimeout(this._recentAlertsStepTimer);
                this._recentAlertsStepTimer = null;
            }
            if (this._recentAlertsScrollRaf != null) {
                cancelAnimationFrame(this._recentAlertsScrollRaf);
                this._recentAlertsScrollRaf = null;
            }
            if (this._recentAlertsBound && this._recentAlertsListEl) {
                this._recentAlertsListEl.removeEventListener("mouseenter", this._recentAlertsBound.enter);
                this._recentAlertsListEl.removeEventListener("mouseleave", this._recentAlertsBound.leave);
                if (this._recentAlertsBound.wheel) {
                    this._recentAlertsListEl.removeEventListener("wheel", this._recentAlertsBound.wheel);
                }
            }
            this._recentAlertsBound = null;
            this._recentAlertsListEl = null;
            this._recentAlertsPaused = false;
        },

        /** ease-out 平滑滚动，避免 scrollTop 瞬变闪烁 */
        animateRecentAlertsScrollTo(ul, targetTop, durationMs, onDone) {
            const maxS = Math.max(0, ul.scrollHeight - ul.clientHeight);
            const target = Math.max(0, Math.min(targetTop, maxS));
            const start = ul.scrollTop;
            const delta = target - start;
            if (Math.abs(delta) < 0.5) {
                if (onDone) onDone();
                return;
            }
            const t0 = performance.now();
            const easeOut = (p) => 1 - (1 - p) ** 3;
            const frame = (now) => {
                const p = Math.min(1, (now - t0) / durationMs);
                ul.scrollTop = start + delta * easeOut(p);
                if (p < 1) {
                    this._recentAlertsScrollRaf = requestAnimationFrame(frame);
                } else {
                    this._recentAlertsScrollRaf = null;
                    if (onDone) onDone();
                }
            };
            if (this._recentAlertsScrollRaf != null) {
                cancelAnimationFrame(this._recentAlertsScrollRaf);
                this._recentAlertsScrollRaf = null;
            }
            this._recentAlertsScrollRaf = requestAnimationFrame(frame);
        },

        /** 未限高前按 DOM 量出前 n 条（至多 3）占用的总高度（px） */
        measureRecentAlertsRowsHeight(ul, rowCount) {
            const items = ul.querySelectorAll("li:not(.recent-alerts-empty)");
            if (!items.length) return 0;
            const n = Math.min(rowCount, items.length);
            const top = items[0].getBoundingClientRect().top;
            const bottom = items[n - 1].getBoundingClientRect().bottom;
            return Math.max(0, Math.ceil(bottom - top));
        },

        /** 固定可视区为恰好 3 条高度；多于 3 条时定时向下滚一行，到底回到顶部 */
        setupRecentAlertsTicker(ul) {
            this.stopRecentAlertsTicker();
            ul.style.maxHeight = "";
            ul.scrollTop = 0;

            const items = ul.querySelectorAll("li:not(.recent-alerts-empty)");
            if (!items.length) return;

            const startTicking = () => {
                const h = this.measureRecentAlertsRowsHeight(ul, 3);
                if (h > 0) ul.style.maxHeight = `${h}px`;

                if (items.length <= 3) return;

                this._recentAlertsListEl = ul;
                const enter = () => {
                    this._recentAlertsPaused = true;
                };
                const leave = () => {
                    this._recentAlertsPaused = false;
                };
                const wheel = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                };
                ul.addEventListener("mouseenter", enter);
                ul.addEventListener("mouseleave", leave);
                ul.addEventListener("wheel", wheel, { passive: false });
                this._recentAlertsBound = { enter, leave, wheel };

                const stepPx = () => {
                    const lis = ul.querySelectorAll("li:not(.recent-alerts-empty)");
                    if (lis.length < 2) return lis[0] ? lis[0].offsetHeight : 64;
                    return lis[1].offsetTop - lis[0].offsetTop;
                };

                const animMs = 520;
                const pauseMs = 1100;

                const scheduleNext = (delay) => {
                    this._recentAlertsStepTimer = setTimeout(doStep, delay);
                };

                const doStep = () => {
                    this._recentAlertsStepTimer = null;
                    if (!this._recentAlertsListEl || this._recentAlertsListEl !== ul) return;
                    if (this._recentAlertsPaused) {
                        scheduleNext(360);
                        return;
                    }
                    const lis = ul.querySelectorAll("li:not(.recent-alerts-empty)");
                    if (lis.length <= 3) return;
                    let step = stepPx();
                    if (step < 8) step = lis[0].offsetHeight + 4;
                    const maxScroll = ul.scrollHeight - ul.clientHeight;
                    if (maxScroll <= 0) return;

                    const afterMove = () => scheduleNext(pauseMs);

                    if (ul.scrollTop >= maxScroll - 2) {
                        ul.scrollTop = 0;
                        afterMove();
                    } else {
                        const nextTop = Math.min(ul.scrollTop + step, maxScroll);
                        this.animateRecentAlertsScrollTo(ul, nextTop, animMs, afterMove);
                    }
                };

                scheduleNext(1200);
            };

            requestAnimationFrame(() => requestAnimationFrame(startTicking));
        },

        async fetchAllUserAlertEvents(userId) {
            const pageSize = 100;
            const maxPages = 50;
            const all = [];
            let offset = 0;
            for (let page = 0; page < maxPages; page += 1) {
                const resp = await fetch(
                    `${S.API_BASE}/api/accounts/users/${userId}/alerts/events?limit=${pageSize}&offset=${offset}&_=${Date.now()}`,
                    {
                        headers: {
                            Authorization: `Bearer ${S.authToken}`,
                            "Cache-Control": "no-cache",
                        },
                        cache: "no-store",
                    }
                );
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(U.extractApiErrorMessage(data));
                }
                const batch = Array.isArray(data.items) ? data.items : [];
                all.push(...batch);
                const hasMore = !!(data.pagination && data.pagination.has_more);
                if (!hasMore || batch.length < pageSize) {
                    break;
                }
                offset += pageSize;
            }
            return all;
        },

        async loadRecentAlertsSummary() {
            const list = document.getElementById("recent-alerts-list");
            if (!list) return;
            const uid = this.resolveDashboardUserId();
            if (!uid || !S.authToken) {
                this.stopRecentAlertsTicker();
                list.style.maxHeight = "";
                list.innerHTML = '<li class="recent-alerts-empty">登录后可查看告警摘要</li>';
                return;
            }
            const gen = ++this._recentAlertsLoadGen;
            try {
                const items = await this.fetchAllUserAlertEvents(uid);
                if (gen !== this._recentAlertsLoadGen) return;
                const stamp = JSON.stringify(
                    items.map((it) => [it.id, it.created_at, it.status, it.message || ""])
                );
                if (list.dataset.alertStamp === stamp) {
                    return;
                }
                list.dataset.alertStamp = stamp;
                this.stopRecentAlertsTicker();
                list.style.maxHeight = "";
                if (!items.length) {
                    list.innerHTML =
                        '<li class="recent-alerts-empty">暂无告警事件，系统运行正常 ✓</li>';
                    return;
                }
                list.innerHTML = items.map((item) => `<li>${U.formatDashboardAlertLine(item)}</li>`).join("");
                this.setupRecentAlertsTicker(list);
            } catch (e) {
                if (gen !== this._recentAlertsLoadGen) return;
                delete list.dataset.alertStamp;
                this.stopRecentAlertsTicker();
                list.style.maxHeight = "";
                const msg = e instanceof Error ? e.message : String(e || "加载失败");
                list.innerHTML = `<li class="recent-alerts-empty">${U.escapeHtml(msg)}</li>`;
            }
        },

        async syncServiceRegistry() {
            const resp = await fetch(`${S.API_BASE}/api/services`, {
                headers: { Authorization: `Bearer ${S.authToken}` },
            });
            if (!resp.ok) {
                throw new Error(`服务注册表加载失败 (${resp.status})`);
            }
            const data = await resp.json();
            const latest = Array.isArray(data) ? data : [];
            const changed = JSON.stringify(latest.map(item => item.id)) !== JSON.stringify(S.serviceRegistry.map(item => item.id));
            S.serviceRegistry = latest;
            if (changed || !document.getElementById("service-content-" + (S.serviceRegistry[0]?.id || ""))) {
                this.renderServiceCardsSkeleton();
            }
        },

        async refreshServiceCard(service) {
            const badge = document.getElementById(`service-badge-${service.id}`);
            const content = document.getElementById(`service-content-${service.id}`);
            if (!badge || !content) return false;

            try {
                const resp = await fetch(`${S.API_BASE}/api/${service.id}/`, {
                    headers: { Authorization: `Bearer ${S.authToken}` },
                });
                const data = await resp.json();
                if (!resp.ok) {
                    this.renderServiceCardError(
                        badge,
                        content,
                        U.extractApiErrorMessage(data) || (`请求失败 (${resp.status})`),
                    );
                    return false;
                }
                if (data.error) {
                    this.renderServiceCardError(badge, content, data.error);
                    return false;
                }
                S.serviceDataCache[service.id] = data;
                this.renderServiceCardSuccess(service, data);
                return true;
            } catch (e) {
                badge.className = "card-badge badge-error";
                badge.textContent = "错误";
                content.innerHTML = `<div class="error-detail">${U.escapeHtml(e.message || "加载失败")}</div>`;
                return false;
            }
        },

        async refreshAll(trigger = "manual") {
            if (S.isRefreshing) {
                if (trigger === "manual") {
                    this.setRefreshFeedback("正在刷新中，请稍候...");
                }
                return;
            }
            this.cancelRefreshFeedbackAutoClear();
            const btn = document.getElementById("refresh-btn");
            S.isRefreshing = true;
            if (btn) {
                btn.disabled = true;
                btn.title = "刷新中...";
                btn.classList.add("spinning");
            }
            this.setRefreshFeedback("刷新中...");
            /** 与额度卡片并行：避免因某个 /api/minimax 等请求挂起导致告警区一直「加载中」 */
            const alertsPromise = this.loadRecentAlertsSummary();
            try {
                await this.syncServiceRegistry();
                await this.syncAccountIdByService();
                const results = await Promise.all(S.serviceRegistry.map(service => this.refreshServiceCard(service)));
                if (results.some(Boolean)) {
                    const now = Date.now();
                    U.saveDashboardCache(now);
                    this.updateLastUpdateText(now);
                } else {
                    this.updateLastUpdateText(Date.now());
                }
                this.setRefreshFeedback("刷新完成");
                this.scheduleRefreshFeedbackAutoClear();
            } catch (e) {
                const msg = e instanceof Error ? e.message : String(e || "未知错误");
                this.setRefreshFeedback(`刷新失败：${msg}`, true);
            } finally {
                await alertsPromise.catch(() => {});
                S.isRefreshing = false;
                if (btn) {
                    btn.classList.remove("spinning");
                    btn.disabled = false;
                    btn.title = "刷新";
                }
            }
        },

        showLoginModal(service) {
            const modal = document.getElementById("login-modal");
            const title = document.getElementById("modal-title");
            const desc = document.getElementById("modal-desc");
            const btn = document.getElementById("modal-login-btn");

            if (service === "minimax") {
                title.textContent = "需要登录 MiniMax";
                desc.textContent = "点击按钮前往 MiniMax 官网登录\n登录完成后返回即可";
                btn.onclick = () => { w.location.href = "https://platform.minimaxi.com/user-center/payment/token-plan"; };
            } else if (service === "xfyun") {
                title.textContent = "需要登录讯飞星辰";
                desc.textContent = "点击按钮前往讯飞登录\n登录完成后返回即可";
                btn.onclick = () => { w.location.href = "https://maas.xfyun.cn/packageSubscription"; };
            }

            modal.style.display = "flex";
        },

        closeModal() {
            document.getElementById("login-modal").style.display = "none";
        },

        boot() {
            this.checkAuth().then(loggedIn => {
                if (loggedIn) {
                    this.renderFromCachedDashboard();
                    /* 最近告警由 refreshAll 首次拉取；勿在此外再并发调用同一函数，避免竞态 */
                    this.refreshAll("init");
                }
            });
            /* 全量刷新服务卡片：默认 60s */
            setInterval(() => {
                if (S.authToken) this.refreshAll("auto");
            }, 60000);
            /* 最近告警单独更频繁拉取（轻量接口），不必去账号页也能接近实时 */
            const ALERTS_POLL_MS = 90_000;
            setInterval(() => {
                if (S.authToken) void this.loadRecentAlertsSummary();
            }, ALERTS_POLL_MS);
            document.addEventListener("visibilitychange", () => {
                if (document.hidden || !S.authToken) return;
                void this.loadRecentAlertsSummary();
            });
        },
    };

    w.TMDApp = App;
    w.refreshAll = (t) => App.refreshAll(t);
    w.logout = () => App.logout();
    w.closeModal = () => App.closeModal();
    w.showLoginModal = (service) => App.showLoginModal(service);

    App.boot();
})(window);
