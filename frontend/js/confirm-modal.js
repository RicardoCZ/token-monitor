/**
 * 全局确认弹窗（Promise + 透明遮罩、无整页压暗）。
 * 首次调用时注入样式与挂载到 document.body。
 *
 * 用法（建议在 ui-shared.js 之后加载）：
 *   if (!(await window.TMDUi.showConfirmModal({ title, message, confirmText: '删除', danger: true }))) return;
 *
 * 选项：title, message, confirmText, cancelText, danger（危险操作用红色主按钮）
 */
(function (w) {
    const STYLE_ID = "tmd-confirm-modal-style";
    const ROOT_ID = "tmd-confirm-modal-root";

    const CSS = `
#${ROOT_ID}.tmd-cm {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    box-sizing: border-box;
    pointer-events: none;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
#${ROOT_ID}.tmd-cm.tmd-cm--open {
    pointer-events: auto;
}
#${ROOT_ID} .tmd-cm__backdrop {
    position: absolute;
    inset: 0;
    background: transparent;
    pointer-events: none;
}
#${ROOT_ID}.tmd-cm--open .tmd-cm__backdrop {
    pointer-events: auto;
}
#${ROOT_ID} .tmd-cm__panel {
    position: relative;
    z-index: 1;
    background: linear-gradient(155deg, #252a42 0%, #1e2238 48%, #1a1e32 100%);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 16px;
    padding: 24px 26px;
    max-width: 400px;
    width: 100%;
    box-shadow:
        0 28px 56px rgba(0, 0, 0, 0.5),
        0 0 0 1px rgba(255, 255, 255, 0.05) inset;
    opacity: 0;
    transform: translateY(18px) scale(0.94);
    transition:
        opacity 0.32s cubic-bezier(0.22, 1, 0.36, 1),
        transform 0.36s cubic-bezier(0.22, 1, 0.36, 1);
}
#${ROOT_ID}.tmd-cm--open .tmd-cm__panel {
    opacity: 1;
    transform: translateY(0) scale(1);
}
#${ROOT_ID} .tmd-cm__title {
    font-size: 17px;
    color: #eceff7;
    margin: 0 0 12px;
    font-weight: 600;
}
#${ROOT_ID} .tmd-cm__msg {
    font-size: 13px;
    color: #b4bdda;
    line-height: 1.5;
    margin: 0 0 20px;
}
#${ROOT_ID} .tmd-cm__actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
}
#${ROOT_ID} .tmd-cm__btn {
    min-width: 88px;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
#${ROOT_ID} .tmd-cm__btn:hover:not(:disabled) {
    transform: translateY(-1px);
}
#${ROOT_ID} .tmd-cm__btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}
#${ROOT_ID} .tmd-cm__btn--primary {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
#${ROOT_ID} .tmd-cm__btn--primary:hover:not(:disabled) {
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}
#${ROOT_ID} .tmd-cm__btn--secondary {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.18);
}
#${ROOT_ID} .tmd-cm__btn--secondary:hover:not(:disabled) {
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
}
#${ROOT_ID} .tmd-cm__btn--danger {
    background: rgba(244, 67, 54, 0.9);
}
#${ROOT_ID} .tmd-cm__btn--danger:hover:not(:disabled) {
    box-shadow: 0 4px 12px rgba(244, 67, 54, 0.45);
}
`;

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }

    function ensureRoot() {
        injectStyles();
        let root = document.getElementById(ROOT_ID);
        if (root) return root;
        root = document.createElement("div");
        root.id = ROOT_ID;
        root.className = "tmd-cm";
        root.setAttribute("role", "dialog");
        root.setAttribute("aria-modal", "true");
        root.setAttribute("aria-hidden", "true");
        root.innerHTML =
            '<div class="tmd-cm__backdrop" aria-hidden="true"></div>' +
            '<div class="tmd-cm__panel">' +
            '<h3 class="tmd-cm__title"></h3>' +
            '<p class="tmd-cm__msg"></p>' +
            '<div class="tmd-cm__actions">' +
            '<button type="button" class="tmd-cm__btn tmd-cm__btn--secondary" data-tmd-cm-cancel>取消</button>' +
            '<button type="button" class="tmd-cm__btn tmd-cm__btn--primary" data-tmd-cm-ok>确定</button>' +
            "</div></div>";
        document.body.appendChild(root);
        return root;
    }

    function showConfirmModal(options) {
        const o = options || {};
        const title = o.title;
        const message = o.message;
        const confirmText = o.confirmText != null ? o.confirmText : "确定";
        const cancelText = o.cancelText != null ? o.cancelText : "取消";
        const danger = !!o.danger;

        return new Promise((resolve) => {
            const overlay = ensureRoot();
            const backdropEl = overlay.querySelector(".tmd-cm__backdrop");
            const titleEl = overlay.querySelector(".tmd-cm__title");
            const msgEl = overlay.querySelector(".tmd-cm__msg");
            const okBtn = overlay.querySelector("[data-tmd-cm-ok]");
            const cancelBtn = overlay.querySelector("[data-tmd-cm-cancel]");
            if (!backdropEl || !titleEl || !msgEl || !okBtn || !cancelBtn) {
                resolve(false);
                return;
            }

            titleEl.textContent = title || "请确认";
            msgEl.textContent = message || "";
            okBtn.textContent = confirmText;
            cancelBtn.textContent = cancelText;
            okBtn.className = "tmd-cm__btn " + (danger ? "tmd-cm__btn--danger" : "tmd-cm__btn--primary");

            const done = (v) => {
                okBtn.onclick = null;
                cancelBtn.onclick = null;
                backdropEl.onclick = null;
                document.removeEventListener("keydown", onKey);
                overlay.classList.remove("tmd-cm--open");
                overlay.setAttribute("aria-hidden", "true");
                resolve(v);
            };
            const onKey = (e) => {
                if (e.key === "Escape") {
                    e.preventDefault();
                    done(false);
                }
            };

            okBtn.onclick = () => done(true);
            cancelBtn.onclick = () => done(false);
            backdropEl.onclick = () => done(false);
            document.addEventListener("keydown", onKey);
            overlay.setAttribute("aria-hidden", "false");
            overlay.classList.add("tmd-cm--open");
            w.requestAnimationFrame(() => {
                w.requestAnimationFrame(() => okBtn.focus());
            });
        });
    }

    const Ui = w.TMDUi || {};
    Ui.showConfirmModal = showConfirmModal;
    w.TMDUi = Ui;
})(window);
