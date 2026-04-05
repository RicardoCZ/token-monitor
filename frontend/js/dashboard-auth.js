/**
 * 仪表盘子页共享：鉴权、Authorization 请求头、顶栏用户区。
 *
 * 依赖（须先于本文件）：api-dashboard-state.js（TMD）、api-dashboard-core.js（TMDCore）、ui-shared.js（TMDUi）
 * 退出确认弹窗：建议在 ui-shared 之后加载 confirm-modal.js（否则 logout 会退回浏览器 confirm）
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

    /**
     * 调用 POST /auth/logout 吊销服务端会话，再清理本地并跳转登录页。
     * @param {object} [options]
     * @param {string} [options.apiBase]
     * @param {string} [options.loginPath] 默认 login.html
     * @param {boolean} [options.skipConfirm] 为 true 时不询问（仅脚本内部等特殊场景）
     * @param {() => void} [options.onAfterClear] 清理 localStorage 之后调用（如 api 页清 sessionStorage）
     */
    async function logout(options) {
        const opts = options || {};
        if (!opts.skipConfirm) {
            if (Ui && typeof Ui.showConfirmModal === "function") {
                const ok = await Ui.showConfirmModal({
                    title: "退出登录",
                    message: "确定要退出当前账号吗？退出后需重新登录。",
                    confirmText: "退出",
                    cancelText: "取消",
                });
                if (!ok) return;
            } else if (!w.confirm("确定要退出当前账号吗？退出后需重新登录。")) {
                return;
            }
        }
        const base =
            opts.apiBase !== undefined && opts.apiBase !== null ? opts.apiBase : S.API_BASE;
        const loginPath = opts.loginPath || "login.html";
        const raw = localStorage.getItem("token");
        if (raw) {
            try {
                await fetch(`${base}/auth/logout`, {
                    method: "POST",
                    headers: { Authorization: `Bearer ${raw}` },
                });
            } catch (e) {
                /* 网络异常：仍执行本地清理 */
            }
        }
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        S.authToken = null;
        S.currentUser = null;
        if (typeof opts.onAfterClear === "function") {
            try {
                opts.onAfterClear();
            } catch (e2) {
                /* ignore */
            }
        }
        w.location.href = loginPath;
    }

    w.TMDAuth = {
        syncTokenFromStorage,
        getAuthHeaders,
        getJsonHeaders,
        checkAuth,
        logout,
        paintUserHeaderBar,
        readCachedUserFromLocalStorage,
    };
})(window);
