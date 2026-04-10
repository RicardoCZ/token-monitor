/**
 * 全局确认弹窗（Promise + 透明遮罩、无整页压暗）。
 * 首次调用时注入样式与挂载到 document.body。
 *
 * 用法（建议在 ui-shared.js 之后加载）：
 *   if (!(await window.TMDUi.showConfirmModal({ title, message, confirmText: '删除', danger: true }))) return;
 * showAlertModal：单按钮提示（只读结果等），点确定或 Esc 或点遮罩后关闭；同样支持 emphasis。
 *
 * 选项：title, message, confirmText, cancelText, danger（危险操作用红色主按钮）
 * emphasis：可选，另起一行显示（如随机密码），字号略大、高亮；不传则不占空间。
 * showConfirmWithPassword：与 showConfirmModal 相同 + 密码输入框；resolve { ok:false }  / { ok:true, password }
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
    margin: 0 0 16px;
}
#${ROOT_ID} .tmd-cm__emphasis {
    font-size: 16px;
    font-weight: 600;
    font-family: ui-monospace, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace;
    letter-spacing: 0.03em;
    color: #f0f3ff;
    line-height: 1.45;
    word-break: break-all;
    margin: 0 0 20px;
    padding: 12px 14px;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.32) 0%, rgba(118, 75, 162, 0.22) 100%);
    border: 1px solid rgba(139, 156, 255, 0.55);
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.06) inset,
        0 4px 14px rgba(102, 126, 234, 0.18);
}
#${ROOT_ID} .tmd-cm__emphasis[hidden] {
    display: none !important;
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
#${ROOT_ID}.tmd-cm--alert .tmd-cm__actions [data-tmd-cm-cancel] {
    display: none !important;
}
#${ROOT_ID}.tmd-cm--alert .tmd-cm__actions {
    justify-content: center;
}
#${ROOT_ID} .tmd-cm__pw-block {
    margin: 0 0 18px;
}
#${ROOT_ID} .tmd-cm__pw-label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: #aeb6d4;
    margin: 0 0 8px;
}
#${ROOT_ID} .tmd-cm__pw-input {
    width: 100%;
    box-sizing: border-box;
    padding: 11px 14px;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(0, 0, 0, 0.28);
    color: #fff;
    font-size: 14px;
}
#${ROOT_ID} .tmd-cm__pw-input:focus {
    outline: none;
    border-color: rgba(102, 126, 234, 0.75);
    box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
}
#${ROOT_ID} .tmd-cm__pw-err {
    font-size: 12px;
    color: #ff8a80;
    margin: 8px 0 0;
    min-height: 1.2em;
}
#${ROOT_ID} .tmd-cm__pw-block[hidden] {
    display: none !important;
}
`;

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }

    function ensurePasswordBlock(overlay) {
        if (overlay.querySelector(".tmd-cm__pw-block")) return;
        const actions = overlay.querySelector(".tmd-cm__actions");
        if (!actions || !actions.parentNode) return;
        const block = document.createElement("div");
        block.className = "tmd-cm__pw-block";
        block.hidden = true;
        block.innerHTML =
            '<label class="tmd-cm__pw-label" for="tmd-cm__pw-input"></label>' +
            '<input type="password" id="tmd-cm__pw-input" class="tmd-cm__pw-input" autocomplete="current-password" />' +
            '<p class="tmd-cm__pw-err" role="alert" hidden></p>';
        actions.parentNode.insertBefore(block, actions);
    }

    function hidePasswordBlock(overlay) {
        const block = overlay.querySelector(".tmd-cm__pw-block");
        const input = overlay.querySelector(".tmd-cm__pw-input");
        const err = overlay.querySelector(".tmd-cm__pw-err");
        if (block) block.hidden = true;
        if (input) {
            input.value = "";
            input.onkeydown = null;
        }
        if (err) {
            err.textContent = "";
            err.hidden = true;
        }
    }

    function ensureRoot() {
        injectStyles();
        let root = document.getElementById(ROOT_ID);
        if (root) {
            if (!root.querySelector(".tmd-cm__emphasis")) {
                const actions = root.querySelector(".tmd-cm__actions");
                if (actions && actions.parentNode) {
                    const emph = document.createElement("p");
                    emph.className = "tmd-cm__emphasis";
                    emph.hidden = true;
                    actions.parentNode.insertBefore(emph, actions);
                }
            }
            ensurePasswordBlock(root);
            return root;
        }
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
            '<p class="tmd-cm__emphasis" hidden></p>' +
            '<div class="tmd-cm__pw-block" hidden>' +
            '<label class="tmd-cm__pw-label" for="tmd-cm__pw-input"></label>' +
            '<input type="password" id="tmd-cm__pw-input" class="tmd-cm__pw-input" autocomplete="current-password" />' +
            '<p class="tmd-cm__pw-err" role="alert" hidden></p>' +
            "</div>" +
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
        const emphasis = o.emphasis;

        return new Promise((resolve) => {
            const overlay = ensureRoot();
            hidePasswordBlock(overlay);
            overlay.classList.remove("tmd-cm--alert");
            const backdropEl = overlay.querySelector(".tmd-cm__backdrop");
            const titleEl = overlay.querySelector(".tmd-cm__title");
            const msgEl = overlay.querySelector(".tmd-cm__msg");
            const emphEl = overlay.querySelector(".tmd-cm__emphasis");
            const okBtn = overlay.querySelector("[data-tmd-cm-ok]");
            const cancelBtn = overlay.querySelector("[data-tmd-cm-cancel]");
            if (!backdropEl || !titleEl || !msgEl || !okBtn || !cancelBtn) {
                resolve(false);
                return;
            }

            titleEl.textContent = title || "请确认";
            msgEl.textContent = message || "";
            if (emphEl) {
                const em = emphasis != null ? String(emphasis).trim() : "";
                if (em) {
                    emphEl.hidden = false;
                    emphEl.textContent = em;
                } else {
                    emphEl.hidden = true;
                    emphEl.textContent = "";
                }
            }
            okBtn.textContent = confirmText;
            cancelBtn.textContent = cancelText;
            okBtn.className = "tmd-cm__btn " + (danger ? "tmd-cm__btn--danger" : "tmd-cm__btn--primary");

            const done = (v) => {
                hidePasswordBlock(overlay);
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

    function showConfirmWithPassword(options) {
        const o = options || {};
        const title = o.title;
        const message = o.message != null ? o.message : "";
        const emphasis = o.emphasis;
        const confirmText = o.confirmText != null ? o.confirmText : "确定";
        const cancelText = o.cancelText != null ? o.cancelText : "取消";
        const danger = !!o.danger;
        const passwordLabel = o.passwordLabel != null ? o.passwordLabel : "当前登录密码";

        return new Promise((resolve) => {
            const overlay = ensureRoot();
            ensurePasswordBlock(overlay);
            hidePasswordBlock(overlay);
            overlay.classList.remove("tmd-cm--alert");
            const backdropEl = overlay.querySelector(".tmd-cm__backdrop");
            const titleEl = overlay.querySelector(".tmd-cm__title");
            const msgEl = overlay.querySelector(".tmd-cm__msg");
            const emphEl = overlay.querySelector(".tmd-cm__emphasis");
            const pwBlock = overlay.querySelector(".tmd-cm__pw-block");
            const pwInput = overlay.querySelector(".tmd-cm__pw-input");
            const pwLabel = overlay.querySelector(".tmd-cm__pw-label");
            const pwErr = overlay.querySelector(".tmd-cm__pw-err");
            const okBtn = overlay.querySelector("[data-tmd-cm-ok]");
            const cancelBtn = overlay.querySelector("[data-tmd-cm-cancel]");
            if (
                !backdropEl ||
                !titleEl ||
                !msgEl ||
                !pwBlock ||
                !pwInput ||
                !pwLabel ||
                !pwErr ||
                !okBtn ||
                !cancelBtn
            ) {
                resolve({ ok: false });
                return;
            }

            titleEl.textContent = title || "请确认";
            msgEl.textContent = message;
            if (emphEl) {
                const em = emphasis != null ? String(emphasis).trim() : "";
                if (em) {
                    emphEl.hidden = false;
                    emphEl.textContent = em;
                } else {
                    emphEl.hidden = true;
                    emphEl.textContent = "";
                }
            }
            pwLabel.textContent = passwordLabel;
            pwErr.textContent = "";
            pwErr.hidden = true;
            pwInput.value = "";
            pwBlock.hidden = false;

            okBtn.textContent = confirmText;
            cancelBtn.textContent = cancelText;
            okBtn.className = "tmd-cm__btn " + (danger ? "tmd-cm__btn--danger" : "tmd-cm__btn--primary");

            const finish = (result) => {
                hidePasswordBlock(overlay);
                okBtn.onclick = null;
                cancelBtn.onclick = null;
                backdropEl.onclick = null;
                pwInput.onkeydown = null;
                document.removeEventListener("keydown", onKey);
                overlay.classList.remove("tmd-cm--open");
                overlay.setAttribute("aria-hidden", "true");
                resolve(result);
            };

            const tryOk = () => {
                const v = (pwInput.value || "").trim();
                if (!v) {
                    pwErr.textContent = "请输入密码";
                    pwErr.hidden = false;
                    return;
                }
                pwErr.hidden = true;
                pwErr.textContent = "";
                finish({ ok: true, password: v });
            };

            const onKey = (e) => {
                if (e.key === "Escape") {
                    e.preventDefault();
                    finish({ ok: false });
                }
            };

            okBtn.onclick = tryOk;
            cancelBtn.onclick = () => finish({ ok: false });
            backdropEl.onclick = () => finish({ ok: false });
            pwInput.onkeydown = (e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    tryOk();
                }
            };
            document.addEventListener("keydown", onKey);
            overlay.setAttribute("aria-hidden", "false");
            overlay.classList.add("tmd-cm--open");
            w.requestAnimationFrame(() => {
                w.requestAnimationFrame(() => pwInput.focus());
            });
        });
    }

    function showAlertModal(options) {
        const o = options || {};
        const title = o.title != null ? o.title : "提示";
        const message = o.message != null ? o.message : "";
        const okText = o.okText != null ? o.okText : "确定";
        const emphasis = o.emphasis;

        return new Promise((resolve) => {
            const overlay = ensureRoot();
            hidePasswordBlock(overlay);
            overlay.classList.add("tmd-cm--alert");
            overlay.classList.remove("tmd-cm--open");
            const backdropEl = overlay.querySelector(".tmd-cm__backdrop");
            const titleEl = overlay.querySelector(".tmd-cm__title");
            const msgEl = overlay.querySelector(".tmd-cm__msg");
            const emphEl = overlay.querySelector(".tmd-cm__emphasis");
            const okBtn = overlay.querySelector("[data-tmd-cm-ok]");
            const cancelBtn = overlay.querySelector("[data-tmd-cm-cancel]");
            if (!backdropEl || !titleEl || !msgEl || !okBtn || !cancelBtn) {
                overlay.classList.remove("tmd-cm--alert");
                resolve();
                return;
            }

            titleEl.textContent = title;
            msgEl.textContent = message;
            if (emphEl) {
                const em = emphasis != null ? String(emphasis).trim() : "";
                if (em) {
                    emphEl.hidden = false;
                    emphEl.textContent = em;
                } else {
                    emphEl.hidden = true;
                    emphEl.textContent = "";
                }
            }
            okBtn.textContent = okText;
            okBtn.className = "tmd-cm__btn tmd-cm__btn--primary";

            const done = () => {
                hidePasswordBlock(overlay);
                okBtn.onclick = null;
                cancelBtn.onclick = null;
                backdropEl.onclick = null;
                document.removeEventListener("keydown", onKey);
                overlay.classList.remove("tmd-cm--open", "tmd-cm--alert");
                overlay.setAttribute("aria-hidden", "true");
                resolve();
            };
            const onKey = (e) => {
                if (e.key === "Escape") {
                    e.preventDefault();
                    done();
                }
            };

            okBtn.onclick = () => done();
            cancelBtn.onclick = null;
            backdropEl.onclick = () => done();
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
    Ui.showConfirmWithPassword = showConfirmWithPassword;
    Ui.showAlertModal = showAlertModal;
    w.TMDUi = Ui;
})(window);
