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
 *   TMDAuth.openChangePassword() — 修改登录密码（顶栏用户名点击入口由 paintUserHeaderBar 绑定）
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
            <span class="header-top-link header-user-name" style="cursor: pointer;" role="button" tabindex="0" title="修改登录密码"
                  onclick="TMDAuth.openChangePassword()"
                  onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();TMDAuth.openChangePassword();}">👤 ${U.escapeHtml(user.username)}</span>
            ${nav}
            <span class="header-top-link" style="cursor: pointer;" role="button" tabindex="0"
                  onclick="logout()" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();logout();}">退出</span>
        `;
    }

    const CHPW_STYLE_ID = "tmd-chpw-style";
    const CHPW_ROOT_ID = "tmd-change-password-root";

    const CHPW_CSS = `
#${CHPW_ROOT_ID}.tmd-chpw {
    position: fixed;
    inset: 0;
    z-index: 10001;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    pointer-events: none;
    visibility: hidden;
    opacity: 0;
    transition: opacity 0.2s ease, visibility 0.2s;
}
#${CHPW_ROOT_ID}.tmd-chpw.tmd-chpw--open {
    pointer-events: auto;
    visibility: visible;
    opacity: 1;
}
#${CHPW_ROOT_ID} .tmd-chpw__backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
}
#${CHPW_ROOT_ID} .tmd-chpw__panel {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 400px;
    background: linear-gradient(155deg, #252a42 0%, #1e2238 48%, #1a1e32 100%);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 16px;
    padding: 22px 24px;
    box-shadow: 0 28px 56px rgba(0, 0, 0, 0.5);
}
#${CHPW_ROOT_ID} .tmd-chpw__title {
    font-size: 17px;
    font-weight: 600;
    color: #eceff7;
    margin: 0 0 6px;
}
#${CHPW_ROOT_ID} .tmd-chpw__hint {
    font-size: 12px;
    color: #8b93b8;
    margin: 0 0 16px;
    line-height: 1.45;
}
#${CHPW_ROOT_ID} .tmd-chpw__err {
    font-size: 13px;
    color: #ff8a80;
    margin: 0 0 12px;
    min-height: 1.2em;
}
#${CHPW_ROOT_ID} .tmd-chpw__field {
    margin-bottom: 14px;
}
#${CHPW_ROOT_ID} .tmd-chpw__field label {
    display: block;
    font-size: 12px;
    color: #b4bdda;
    margin-bottom: 6px;
}
#${CHPW_ROOT_ID} .tmd-chpw__field input {
    width: 100%;
    box-sizing: border-box;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.18);
    background: rgba(0, 0, 0, 0.25);
    color: #fff;
    font-size: 14px;
}
#${CHPW_ROOT_ID} .tmd-chpw__field input:focus {
    outline: none;
    border-color: rgba(102, 126, 234, 0.85);
}
#${CHPW_ROOT_ID} .tmd-chpw__actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    margin-top: 8px;
}
#${CHPW_ROOT_ID} .tmd-chpw__btn {
    min-width: 88px;
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    color: #fff;
}
#${CHPW_ROOT_ID} .tmd-chpw__btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
}
#${CHPW_ROOT_ID} .tmd-chpw__btn--secondary {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
#${CHPW_ROOT_ID} .tmd-chpw__btn--primary {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
`;

    function injectChangePasswordStyles() {
        if (document.getElementById(CHPW_STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = CHPW_STYLE_ID;
        style.textContent = CHPW_CSS;
        document.head.appendChild(style);
    }

    function validateNewLoginPassword(s) {
        if (s.length < 8) return "密码至少8位";
        if (!/[A-Z]/.test(s)) return "密码须包含大写字母";
        if (!/[a-z]/.test(s)) return "密码须包含小写字母";
        if (!/\d/.test(s)) return "密码须包含数字";
        return "";
    }

    function normalizeChangePasswordDetail(data) {
        const d = data && data.detail;
        if (d == null) return "请求失败";
        if (typeof d === "string") return d;
        if (Array.isArray(d)) {
            return d
                .map(function (x) {
                    if (x && typeof x === "object" && (x.msg || x.message)) {
                        return String(x.msg || x.message);
                    }
                    return String(x);
                })
                .join("；");
        }
        return "请求失败";
    }

    function ensureChangePasswordRoot() {
        injectChangePasswordStyles();
        let root = document.getElementById(CHPW_ROOT_ID);
        if (root) return root;
        root = document.createElement("div");
        root.id = CHPW_ROOT_ID;
        root.className = "tmd-chpw";
        root.setAttribute("role", "dialog");
        root.setAttribute("aria-modal", "true");
        root.innerHTML =
            '<div class="tmd-chpw__backdrop" aria-hidden="true"></div>' +
            '<div class="tmd-chpw__panel">' +
            '<h3 class="tmd-chpw__title">修改登录密码</h3>' +
            '<p class="tmd-chpw__hint">修改成功后其它设备上的登录将失效，需重新登录。</p>' +
            '<div class="tmd-chpw__err" aria-live="polite"></div>' +
            '<div class="tmd-chpw__field"><label for="tmd-chpw-current">当前密码</label>' +
            '<input type="password" id="tmd-chpw-current" autocomplete="current-password" /></div>' +
            '<div class="tmd-chpw__field"><label for="tmd-chpw-new">新密码</label>' +
            '<input type="password" id="tmd-chpw-new" autocomplete="new-password" /></div>' +
            '<div class="tmd-chpw__field"><label for="tmd-chpw-new2">确认新密码</label>' +
            '<input type="password" id="tmd-chpw-new2" autocomplete="new-password" /></div>' +
            '<div class="tmd-chpw__actions">' +
            '<button type="button" class="tmd-chpw__btn tmd-chpw__btn--secondary" data-tmd-chpw-cancel>取消</button>' +
            '<button type="button" class="tmd-chpw__btn tmd-chpw__btn--primary" data-tmd-chpw-save>保存</button>' +
            "</div></div>";
        document.body.appendChild(root);

        const backdrop = root.querySelector(".tmd-chpw__backdrop");
        const cancelBtn = root.querySelector("[data-tmd-chpw-cancel]");
        const saveBtn = root.querySelector("[data-tmd-chpw-save]");
        const errEl = root.querySelector(".tmd-chpw__err");
        const curEl = root.querySelector("#tmd-chpw-current");
        const n1El = root.querySelector("#tmd-chpw-new");
        const n2El = root.querySelector("#tmd-chpw-new2");

        function closeChpw() {
            root.classList.remove("tmd-chpw--open");
            document.removeEventListener("keydown", onDocKey);
            if (errEl) errEl.textContent = "";
            if (curEl) curEl.value = "";
            if (n1El) n1El.value = "";
            if (n2El) n2El.value = "";
        }

        function onDocKey(e) {
            if (e.key === "Escape") {
                e.preventDefault();
                closeChpw();
            }
        }

        async function onSave() {
            if (!errEl || !curEl || !n1El || !n2El || !saveBtn) return;
            errEl.textContent = "";
            const current = curEl.value;
            const n1 = n1El.value;
            const n2 = n2El.value;
            if (!current) {
                errEl.textContent = "请填写当前密码";
                return;
            }
            const pErr = validateNewLoginPassword(n1);
            if (pErr) {
                errEl.textContent = pErr;
                return;
            }
            if (n1 !== n2) {
                errEl.textContent = "两次输入的新密码不一致";
                return;
            }
            saveBtn.disabled = true;
            try {
                const resp = await fetch(`${S.API_BASE}/auth/change-password`, {
                    method: "POST",
                    headers: getJsonHeaders(),
                    body: JSON.stringify({
                        current_password: current,
                        new_password: n1,
                    }),
                });
                let data = {};
                try {
                    data = await resp.json();
                } catch (e1) {
                    data = {};
                }
                if (!resp.ok) {
                    errEl.textContent = normalizeChangePasswordDetail(data);
                    return;
                }
                localStorage.setItem("token", data.access_token);
                localStorage.setItem(
                    "user",
                    JSON.stringify({
                        id: data.user_id,
                        username: data.username,
                        role: data.role,
                    })
                );
                syncTokenFromStorage();
                if (S.currentUser && typeof S.currentUser === "object") {
                    S.currentUser.username = data.username;
                    S.currentUser.role = data.role;
                }
                closeChpw();
                if (Ui && typeof Ui.showToast === "function") {
                    Ui.showToast("登录密码已更新");
                }
            } catch (e) {
                errEl.textContent = "网络错误：" + (e.message || String(e));
            } finally {
                saveBtn.disabled = false;
            }
        }

        if (backdrop) backdrop.addEventListener("click", closeChpw);
        if (cancelBtn) cancelBtn.addEventListener("click", closeChpw);
        if (saveBtn) saveBtn.addEventListener("click", onSave);

        root._tmdChpwClose = closeChpw;
        root._tmdChpwOpen = function () {
            errEl.textContent = "";
            if (curEl) curEl.value = "";
            if (n1El) n1El.value = "";
            if (n2El) n2El.value = "";
            root.classList.add("tmd-chpw--open");
            document.addEventListener("keydown", onDocKey);
            w.requestAnimationFrame(function () {
                w.requestAnimationFrame(function () {
                    if (curEl) curEl.focus();
                });
            });
        };
        return root;
    }

    function openChangePassword() {
        const root = ensureChangePasswordRoot();
        if (root && typeof root._tmdChpwOpen === "function") root._tmdChpwOpen();
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
        openChangePassword,
    };
})(window);
