/**
 * 仪表盘子页共享：鉴权、Authorization 请求头、顶栏用户区。
 *
 * 依赖（须先于本文件）：api-dashboard-state.js（TMD）、api-dashboard-core.js（TMDCore）、ui-shared.js（TMDUi）
 *
 * 用法：
 *   TMDAuth.syncTokenFromStorage();
 *   fetch(`${TMD.API_BASE}/api/foo`, { headers: TMDAuth.getAuthHeaders() });
 *   await TMDAuth.checkAuth({ requireAdmin: true, ... });
 */
(function (w) {
    const S = w.TMD;
    if (!S) {
        console.warn("[dashboard-auth] 请先加载 api-dashboard-state.js（window.TMD）");
        return;
    }
    const U = w.TMDCore;
    const Ui = w.TMDUi;
    if (!U) {
        console.warn("[dashboard-auth] 请先加载 api-dashboard-core.js（window.TMDCore）");
    }

    function syncTokenFromStorage() {
        const t = localStorage.getItem("token");
        S.authToken = t;
        return t;
    }

    function getAuthHeaders() {
        syncTokenFromStorage();
        return { Authorization: `Bearer ${S.authToken}` };
    }

    function getJsonHeaders() {
        return {
            ...getAuthHeaders(),
            "Content-Type": "application/json",
        };
    }

    function readCachedUserFromLocalStorage() {
        try {
            const raw = localStorage.getItem("user");
            if (!raw) return null;
            const u = JSON.parse(raw);
            if (!u || typeof u.username !== "string") return null;
            return {
                id: u.id,
                username: u.username,
                role: u.role === "admin" ? "admin" : "user",
            };
        } catch (e) {
            return null;
        }
    }

    function paintUserHeaderBar(user, options) {
        const opts = options || {};
        const userInfoId = opts.userInfoId || "user-info";
        const el = document.getElementById(userInfoId);
        if (!el || !user) return;

        const forceAdmin = !!opts.forceShowAdminLink;
        const showAdminLink = forceAdmin || user.role === "admin";
        const nav =
            Ui && typeof Ui.buildTopNavLinks === "function"
                ? Ui.buildTopNavLinks(S.CURRENT_PAGE, { showAdminLink })
                : "";

        el.innerHTML = `
            <span>👤 ${U.escapeHtml(user.username)}</span>
            ${nav}
            <span class="header-top-link" style="cursor: pointer;" role="button" tabindex="0"
                  onclick="logout()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();logout();}">退出</span>
        `;
    }

    /**
     * @param {object} [options]
     * @param {string} [options.apiBase] 覆盖 TMD.API_BASE（如设置页走相对路径或本机端口）
     * @param {boolean} [options.requireAdmin] 非管理员则失败
     * @param {(user: object) => void} [options.onNotAdmin]
     * @param {boolean} [options.forceShowAdminLink] 顶栏始终展示管理后台入口
     * @param {boolean} [options.prefillHeaderFromCache] 在请求 /auth/me 前用 localStorage.user 先渲染顶栏
     * @param {boolean} [options.persistUserToLocalStorage] 为 true 时将 /auth/me 写入 localStorage.user（设置页首屏）
     * @param {string} [options.userInfoId]
     * @param {(err: Error) => void} [options.onNetworkError]
     */
    async function checkAuth(options) {
        const opts = options || {};
        const base =
            opts.apiBase !== undefined && opts.apiBase !== null ? opts.apiBase : S.API_BASE;

        syncTokenFromStorage();

        if (!S.authToken) {
            w.location.href = "login.html";
            return false;
        }

        if (opts.prefillHeaderFromCache) {
            const cached = readCachedUserFromLocalStorage();
            paintUserHeaderBar(cached || { username: "…", role: "user" }, opts);
        }

        try {
            const resp = await fetch(`${base}/auth/me`, {
                headers: { Authorization: `Bearer ${S.authToken}` },
            });

            if (!resp.ok) {
                localStorage.removeItem("token");
                localStorage.removeItem("user");
                w.location.href = "login.html";
                return false;
            }

            const user = await resp.json();
            S.currentUser = user;

            if (opts.requireAdmin && user.role !== "admin") {
                if (typeof opts.onNotAdmin === "function") {
                    opts.onNotAdmin(user);
                } else if (Ui && typeof Ui.showToast === "function") {
                    Ui.showToast("需要管理员权限", true);
                    setTimeout(() => {
                        w.location.href = "api.html";
                    }, 1500);
                }
                return false;
            }

            if (opts.persistUserToLocalStorage === true) {
                try {
                    localStorage.setItem(
                        "user",
                        JSON.stringify({
                            id: user.id,
                            username: user.username,
                            role: user.role,
                        })
                    );
                } catch (e2) {
                    /* ignore */
                }
            }

            paintUserHeaderBar(user, opts);
            return true;
        } catch (e) {
            if (typeof opts.onNetworkError === "function") {
                opts.onNetworkError(e);
            } else if (Ui && typeof Ui.showToast === "function") {
                Ui.showToast("网络错误: " + e.message, true);
            } else {
                console.error("[TMDAuth] checkAuth:", e);
            }
            return false;
        }
    }

    w.TMDAuth = {
        syncTokenFromStorage,
        getAuthHeaders,
        getJsonHeaders,
        checkAuth,
        paintUserHeaderBar,
        readCachedUserFromLocalStorage,
    };
})(window);
