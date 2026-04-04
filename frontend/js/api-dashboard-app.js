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
            const links = [
                { path: "api.html", label: "📊 实时监控" },
                { path: "history.html", label: "📈 历史趋势" },
                { path: "setup.html", label: "🔧 设置凭证" },
                { path: "accounts.html", label: "🧾 账号管理" },
            ];
            if (isAdmin) {
                links.push({ path: "admin.html", label: "⚙️ 管理后台" });
            }
            return links
                .filter(item => item.path.toLowerCase() !== S.CURRENT_PAGE)
                .map(item => `<a href="${item.path}" class="header-top-link">${item.label}</a>`)
                .join("");
        },

        setRefreshFeedback(text, isError = false) {
            const el = document.getElementById("refresh-feedback");
            if (!el) return;
            el.textContent = text || "";
            el.className = "refresh-feedback" + (isError ? " error" : "");
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
                        <span class="card-title">${U.escapeHtml(service.icon || "🧩")} ${U.escapeHtml(service.name || service.id)}</span>
                        <span class="card-badge badge-ok" id="service-badge-${U.escapeHtml(service.id)}">加载中</span>
                    </div>
                    <div class="service-card-content" id="service-content-${U.escapeHtml(service.id)}">
                        <div class="loading">正在查询 ${U.escapeHtml(service.name || service.id)} 额度</div>
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

        renderServiceCardSuccess(service, data) {
            const badge = document.getElementById(`service-badge-${service.id}`);
            const content = document.getElementById(`service-content-${service.id}`);
            if (!badge || !content) return;
            badge.className = "card-badge badge-ok";
            badge.textContent = "正常";

            const { rows, usage } = U.buildMetricRows(service, data);
            const percent = U.getNumberValue(usage.percent);
            const colorClass = percent > 80 ? "red" : percent > 50 ? "orange" : "green";

            const metaRows = [{ label: "到期时间", value: usage.expiresAt || "-" }];
            if (service.id !== "xfyun") {
                metaRows.push({
                    label: "重置时间",
                    value: U.formatResetTime(usage.resetHours, usage.resetMinutes),
                });
            }

            content.innerHTML = `
                <div class="card-stats-block">
                    ${rows.map(row => `
                        <div class="stat-row">
                            <span class="stat-label">${U.escapeHtml(row.label)}</span>
                            <span class="stat-value">${U.escapeHtml(row.value)}</span>
                        </div>
                    `).join("")}
                </div>
                <div class="card-meta-block">
                    ${metaRows.map((row, idx) => `
                        <div class="stat-row ${idx === 0 ? "meta-row-first" : ""}">
                            <span class="stat-label">${U.escapeHtml(row.label)}</span>
                            <span class="stat-value">${U.escapeHtml(row.value)}</span>
                        </div>
                    `).join("")}
                </div>
                <div class="card-progress-wrap">
                    <div class="progress-bar">
                        <div class="progress-fill ${colorClass}" style="width: ${Math.max(0, Math.min(100, percent))}%"></div>
                    </div>
                </div>
            `;
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
            return true;
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
            const btn = document.getElementById("refresh-btn");
            S.isRefreshing = true;
            if (btn) {
                btn.disabled = true;
                btn.title = "刷新中...";
                btn.classList.add("spinning");
            }
            this.setRefreshFeedback("刷新中...");
            try {
                await this.syncServiceRegistry();
                const results = await Promise.all(S.serviceRegistry.map(service => this.refreshServiceCard(service)));
                if (results.some(Boolean)) {
                    const now = Date.now();
                    U.saveDashboardCache(now);
                    this.updateLastUpdateText(now);
                } else {
                    this.updateLastUpdateText(Date.now());
                }
                this.setRefreshFeedback("刷新完成");
            } catch (e) {
                const msg = e instanceof Error ? e.message : String(e || "未知错误");
                this.setRefreshFeedback(`刷新失败：${msg}`, true);
            } finally {
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
                    this.refreshAll("init");
                }
            });
            setInterval(() => {
                if (S.authToken) this.refreshAll("auto");
            }, 60000);
        },
    };

    w.TMDApp = App;
    w.refreshAll = (t) => App.refreshAll(t);
    w.logout = () => App.logout();
    w.closeModal = () => App.closeModal();
    w.showLoginModal = (service) => App.showLoginModal(service);

    App.boot();
})(window);
