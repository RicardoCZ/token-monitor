/**
 * 多页面共享 UI：Toast、顶部导航链接、原生 <select> 自定义下拉。
 * 确认弹窗见 js/confirm-modal.js → window.TMDUi.showConfirmModal（与下文 Object.assign 合并，任意顺序加载均可）。
 * 鉴权与请求头见 js/dashboard-auth.js → window.TMDAuth（在 state、core、本文件之后加载）。
 * 依赖：先加载 api-dashboard-state.js、api-dashboard-core.js（window.TMDCore）。
 */
(function (w) {
    const customSelectRegistry = new Map();
    let customSelectGlobalCloseBound = false;

    function escapeHtml(text) {
        return w.TMDCore.escapeHtml(text);
    }

    function ensureCustomSelectGlobalCloseHandler() {
        if (customSelectGlobalCloseBound) return;
        document.addEventListener("click", (event) => {
            document.querySelectorAll(".custom-select.open").forEach((root) => {
                if (!root.contains(event.target)) root.classList.remove("open");
            });
        });
        customSelectGlobalCloseBound = true;
    }

    function bindCustomSelectElement(select, options = {}) {
        if (!select || select.tagName !== "SELECT") return;
        ensureCustomSelectGlobalCloseHandler();
        const selectId = options.selectId || select.id || "";
        let root = null;
        const existingId = select.dataset.customSelectId || "";
        if (existingId) root = document.getElementById(existingId);

        if (!root) {
            const suffix = selectId || `inline-${Math.random().toString(36).slice(2, 8)}`;
            const customId = `custom-${suffix}`;
            root = document.createElement("div");
            root.className = "custom-select";
            root.id = customId;
            root.innerHTML = `
                    <div class="custom-select-trigger"></div>
                    <ul class="custom-select-options"></ul>
                `;
            select.insertAdjacentElement("afterend", root);
            select.classList.add("native-select-hidden");
            select.dataset.customSelectId = customId;
            root.querySelector(".custom-select-trigger")?.addEventListener("click", (event) => {
                event.stopPropagation();
                root.classList.toggle("open");
            });
            root.querySelector(".custom-select-options")?.addEventListener("click", (event) => {
                const target = event.target;
                if (!(target instanceof HTMLElement)) return;
                const item = target.closest("li[data-value]");
                if (!item) return;
                const nextValue = item.getAttribute("data-value") ?? "";
                const optIdx = Array.from(select.options).findIndex(
                    (o) => String(o.value ?? "") === String(nextValue)
                );
                if (optIdx < 0) return;
                if (select.selectedIndex !== optIdx) {
                    select.selectedIndex = optIdx;
                    const trig = root.querySelector(".custom-select-trigger");
                    const lst = root.querySelector(".custom-select-options");
                    const ao = select.options[optIdx] || null;
                    if (trig) {
                        trig.textContent = ao ? String(ao.textContent || "").trim() : "请选择";
                    }
                    if (lst) {
                        const cur = String(ao?.value ?? "");
                        lst.querySelectorAll("li[data-value]").forEach((li) => {
                            const v = li.getAttribute("data-value") ?? "";
                            li.classList.toggle("active", v === cur);
                        });
                    }
                    select.dispatchEvent(new Event("change", { bubbles: true }));
                }
                root.classList.remove("open");
            });
        }

        const trigger = root.querySelector(".custom-select-trigger");
        const list = root.querySelector(".custom-select-options");
        if (!trigger || !list) return;

        const currentValue = String(select.value ?? "");
        const optionItems = Array.from(select.options).map((opt) => {
            const val = String(opt.value ?? "");
            const text = String(opt.textContent ?? "").trim();
            const activeClass = val === currentValue ? "active" : "";
            return `<li data-value="${escapeHtml(val)}" class="${activeClass}">${escapeHtml(text)}</li>`;
        });
        list.innerHTML = optionItems.join("");

        const activeOption = select.options[select.selectedIndex] || select.options[0] || null;
        trigger.textContent = activeOption ? String(activeOption.textContent || "").trim() : "请选择";

        if (selectId) customSelectRegistry.set(selectId, root.id);
    }

    function bindCustomSelectById(selectId, options = {}) {
        const select = document.getElementById(selectId);
        if (!select || select.tagName !== "SELECT") return;
        bindCustomSelectElement(select, { ...options, selectId });
    }

    function refreshCustomSelect(selectId) {
        bindCustomSelectById(selectId);
    }

    function showToast(msg, isError = false, toastId = "toast") {
        const toast = document.getElementById(toastId);
        if (!toast) return;
        toast.textContent = msg;
        toast.className = "toast show" + (isError ? " error" : "");
        setTimeout(() => {
            toast.className = "toast";
        }, 3000);
    }

    /** 与 location 片段对齐，便于正确隐藏「当前页」链接（如 history ↔ history.html） */
    function normalizeNavPageKey(raw) {
        const s = String(raw || "").trim().toLowerCase().split(/[?#]/)[0];
        const parts = s.split("/").filter(Boolean);
        const leaf = parts[parts.length - 1] || "";
        if (!leaf) return "";
        if (leaf.endsWith(".html")) return leaf;
        return `${leaf}.html`;
    }

    function buildTopNavLinks(currentPageLower, opts = {}) {
        const showAdminLink = !!opts.showAdminLink;
        const page = normalizeNavPageKey(currentPageLower);
        const links = [
            { path: "api.html", label: "📊 实时监控" },
            { path: "alerts.html", label: "🚨 规则与事件" },
            { path: "history.html", label: "📈 历史趋势" },
            { path: "setup.html", label: "🔧 设置凭证" },
            { path: "accounts.html", label: "🧾 账号管理" },
        ];
        if (showAdminLink) {
            links.push({ path: "admin.html", label: "⚙️ 管理后台" });
        }
        const nav = links
            .filter((item) => item.path.toLowerCase() !== page)
            .map((item) => `<a href="${item.path}" class="header-top-link">${item.label}</a>`)
            .join("");
        const apk = `<a href="/api/latest-android-apk" class="header-top-link" download title="项目根目录 android-apk 下按修改时间最新的 .apk">下载 APK</a>`;
        return nav + apk;
    }

    w.TMDUi = Object.assign({}, w.TMDUi || {}, {
        showToast,
        buildTopNavLinks,
        bindCustomSelectById,
        bindCustomSelectElement,
        refreshCustomSelect,
    });
})(window);
