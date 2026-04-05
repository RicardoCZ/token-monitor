/**
 * 共享工具与监控指标解析（window.TMDCore）
 *
 * 依赖：先加载 api-dashboard-state.js（window.TMD）。
 * api.html：state → core → ui-shared → app；其它页面在 state + core 之后按需加载 ui-shared.js。
 * 账号/管理页等可再加载 ui-shared.js（window.TMDUi）。
 */
(function (w) {
    const S = w.TMD;

    w.TMDCore = {
        escapeHtml(text) {
            const div = document.createElement("div");
            div.textContent = text == null ? "" : String(text);
            return div.innerHTML;
        },

        escapeAttr(text) {
            return String(text ?? "")
                .replace(/&/g, "&amp;")
                .replace(/"/g, "&quot;")
                .replace(/</g, "&lt;");
        },

        /** 服务注册表 icon 可为 emoji 或静态资源路径（如 /icons/minimax.ico） */
        isServiceIconUrl(icon) {
            const s = String(icon || "").trim();
            if (!s) return false;
            if (s.startsWith("/icons/") || s.startsWith("http://") || s.startsWith("https://")) return true;
            return /\.(ico|png|webp|svg|gif)$/i.test(s);
        },

        renderServiceIconHtml(icon, alt = "") {
            const s = String(icon || "").trim();
            if (!s) return "";
            if (this.isServiceIconUrl(s)) {
                const src = this.escapeAttr(s);
                const altEsc = this.escapeAttr(alt);
                return `<img class="tm-service-icon" src="${src}" alt="${altEsc}" width="20" height="20" loading="lazy" decoding="async" />`;
            }
            return this.escapeHtml(s);
        },

        formatUnit(unit) {
            const key = String(unit || "").toLowerCase();
            if (!key) return "";
            if (key === "percent") return "%";
            if (key === "count") return "次";
            if (key === "w") return "万";
            return unit;
        },

        normalizeMetricDefs(metricDefs) {
            if (!Array.isArray(metricDefs)) return [];
            const defs = metricDefs
                .filter(item => item && typeof item === "object")
                .map(item => ({
                    key: String(item.key || "").trim(),
                    label: String(item.label || item.key || "").trim(),
                    unit: String(item.unit || "").trim(),
                }))
                .filter(item => item.key);

            const deduped = [];
            const seen = new Set();
            for (const item of defs) {
                if (seen.has(item.key)) continue;
                seen.add(item.key);
                deduped.push(item);
            }
            return deduped;
        },

        /** FastAPI HTTPException / 旧版 body.error */
        extractApiErrorMessage(data) {
            if (!data || typeof data !== "object") return "加载失败";
            if (typeof data.detail === "string") return data.detail;
            if (Array.isArray(data.detail)) {
                const parts = data.detail.map(e => (e && (e.msg || e.message)) || "").filter(Boolean);
                return parts.length ? parts.join(" ") : "请求无效";
            }
            if (data.error) return String(data.error);
            return "";
        },

        getNumberValue(value) {
            const n = Number(value);
            return Number.isFinite(n) ? n : 0;
        },

        /** 图表等场景：非数值返回 null（与 getNumberValue 默认 0 区分） */
        getNullableNumber(value) {
            const n = Number(value);
            return Number.isFinite(n) ? n : null;
        },

        buildUsageNumbers(data) {
            const pageInfo = data?.page_info || {};
            const used = this.getNumberValue(pageInfo.used);
            const total = this.getNumberValue(pageInfo.total);
            const remainFromPage = pageInfo.remain;
            const remain = remainFromPage != null ? this.getNumberValue(remainFromPage) : Math.max(0, total - used);
            const percentRaw = pageInfo.percent ?? data?.percent;
            const percent = percentRaw != null ? this.getNumberValue(percentRaw) : (total > 0 ? (used / total) * 100 : 0);
            const expiresAtRaw =
                pageInfo.expiresAt ??
                pageInfo.expires_at ??
                pageInfo.expireAt ??
                pageInfo.expire_at ??
                data?.expiresAt ??
                data?.expires_at;
            const resetCaptionRaw = pageInfo.resetCaption ?? pageInfo.reset_caption ?? "";
            return {
                used,
                total,
                remain,
                percent,
                expiresAt: expiresAtRaw ? String(expiresAtRaw) : "-",
                resetHours: this.getNumberValue(pageInfo.resetHours ?? pageInfo.reset_hours),
                resetMinutes: this.getNumberValue(pageInfo.resetMinutes ?? pageInfo.reset_minutes),
                resetCaption: String(resetCaptionRaw || "").trim(),
                raw: pageInfo,
            };
        },

        pickMetricValue(metricKey, usage) {
            const key = String(metricKey || "").trim().toLowerCase();
            if (key === "used") return usage.used;
            if (key === "total") return usage.total;
            if (key === "percent") return usage.percent;
            if (key === "remain") return usage.remain;
            return null;
        },

        formatMetricValue(value, unit, metricKey) {
            const numeric = this.getNumberValue(value);
            if (String(unit || "").toLowerCase() === "percent" || String(metricKey || "").toLowerCase().includes("percent")) {
                return `${numeric.toFixed(1)}%`;
            }
            const unitText = this.formatUnit(unit);
            if (!unitText) return `${numeric}`;
            return `${numeric} ${unitText}`.trim();
        },

        buildMetricRows(service, data) {
            const usage = this.buildUsageNumbers(data);
            const defs = this.normalizeMetricDefs(service.metric_defs);
            const rows = [];
            const renderedKeys = new Set();
            for (const def of defs) {
                const value = this.pickMetricValue(def.key, usage);
                if (value == null) continue;
                renderedKeys.add(String(def.key || "").trim().toLowerCase());
                rows.push({
                    label: def.label || def.key,
                    value: this.formatMetricValue(value, def.unit, def.key),
                });
            }
            if (!renderedKeys.has("remain")) {
                const totalDef = defs.find(def => String(def.key || "").trim().toLowerCase() === "total");
                const usedDef = defs.find(def => String(def.key || "").trim().toLowerCase() === "used");
                const remainUnit = (totalDef && totalDef.unit) || (usedDef && usedDef.unit) || "";
                rows.push({
                    label: "剩余",
                    value: this.formatMetricValue(usage.remain, remainUnit, "remain"),
                });
            }
            if (!rows.length) {
                rows.push({ label: "已用", value: `${usage.used}` });
                rows.push({ label: "总量", value: `${usage.total}` });
                rows.push({ label: "剩余", value: `${usage.remain}` });
                rows.push({ label: "使用率", value: `${usage.percent.toFixed(1)}%` });
            }
            return { rows, usage };
        },

        formatResetTime(resetHours, resetMinutes) {
            if (resetHours > 0 || resetMinutes > 0) {
                return `${resetHours || 0}小时${resetMinutes || 0}分钟`;
            }
            return "-";
        },

        saveDashboardCache(updatedAt = Date.now()) {
            try {
                const payload = {
                    updatedAt,
                    registry: Array.isArray(S.serviceRegistry) ? S.serviceRegistry : [],
                    dataByService: S.serviceDataCache || {},
                };
                sessionStorage.setItem(S.DASHBOARD_CACHE_KEY, JSON.stringify(payload));
            } catch (e) {
                // ignore
            }
        },

        loadDashboardCache() {
            try {
                const raw = sessionStorage.getItem(S.DASHBOARD_CACHE_KEY);
                if (!raw) return null;
                const parsed = JSON.parse(raw);
                if (!parsed || typeof parsed !== "object") return null;
                if (!Array.isArray(parsed.registry) || typeof parsed.dataByService !== "object") return null;
                return parsed;
            } catch (e) {
                return null;
            }
        },

        /**
         * 监控卡片用小折线图。竖直域按数据 min–max 自适应（带少量内边距），避免在矮条里用满量程 0–100 时曲线被压成平线；
         * 与历史趋势大图刻度不必一致，以小图可读性优先。
         */
        buildSparklineSvg(percentSeries, strokeColor = "#6f88ff") {
            const vals = Array.isArray(percentSeries)
                ? percentSeries.map((v) => this.getNumberValue(v)).filter((n) => Number.isFinite(n))
                : [];
            const w = 200;
            const h = 52;
            const padX = 6;
            const padY = 10;
            if (vals.length < 2) {
                return `<svg class="sparkline-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><text x="8" y="30" fill="rgba(168,176,211,0.75)" font-size="11">暂无足够数据</text></svg>`;
            }
            let minV = Math.min(...vals);
            let maxV = Math.max(...vals);
            if (maxV - minV < 1e-6) {
                minV = Math.max(0, minV - 5);
                maxV = Math.min(100, maxV + 5);
            } else {
                const pad = (maxV - minV) * 0.12;
                minV = Math.max(0, minV - pad);
                maxV = Math.min(100, maxV + pad);
            }
            const span = Math.max(1e-6, maxV - minV);
            const innerW = w - padX * 2;
            const innerH = h - padY * 2;
            const line = vals
                .map((v, i) => {
                    const x = padX + (i / (vals.length - 1)) * innerW;
                    const y = padY + (1 - (v - minV) / span) * innerH;
                    return `${x.toFixed(2)},${y.toFixed(2)}`;
                })
                .join(" ");
            /* 底边收到 y=h 铺满底部；左右仍与折线两端对齐，避免拉到 0/w 产生斜向补边 */
            const area = `${padX},${h} ${line} ${w - padX},${h}`;
            const raw = String(strokeColor || "#6f88ff").trim();
            const safeStroke = /^#[0-9a-fA-F]{6}$/.test(raw) ? raw : "#6f88ff";
            const gid = `sf${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
            return (
                `<svg class="sparkline-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
                `<defs>` +
                `<linearGradient id="${gid}-area" x1="0" y1="0" x2="0" y2="1">` +
                `<stop offset="0%" stop-color="${safeStroke}" stop-opacity="0.28"/>` +
                `<stop offset="38%" stop-color="${safeStroke}" stop-opacity="0.09"/>` +
                `<stop offset="100%" stop-color="${safeStroke}" stop-opacity="0"/>` +
                `</linearGradient>` +
                `</defs>` +
                `<polygon class="sparkline-area" points="${area}" fill="url(#${gid}-area)" />` +
                `<polyline class="sparkline-halo" points="${line}" fill="none" stroke="${safeStroke}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.11"/>` +
                `<polyline class="sparkline-line" points="${line}" fill="none" stroke="${safeStroke}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>` +
                `</svg>`
            );
        },

        serviceIdToShortLabel(serviceId) {
            const k = String(serviceId || "").toLowerCase();
            if (k === "minimax") return "MiniMax";
            if (k === "xfyun") return "讯飞";
            return serviceId || "-";
        },

        alertEventEmoji(status) {
            const key = String(status || "").trim().toLowerCase();
            if (key === "recovered" || key === "ok") return "🟢";
            if (key === "triggered" || key === "holding") return "🔴";
            return "🟠";
        },

        /** 与账号页解析规则对齐的简短文案（监控摘要） */
        formatDashboardAlertLine(item) {
            const acc = this.escapeHtml(item.account_name || `账号#${item.account_id || ""}`);
            const svc = this.escapeHtml(this.serviceIdToShortLabel(item.service_id));
            const msgRaw = String(item.message || "").trim();
            let detail = this.escapeHtml(msgRaw || "-");
            const matched = msgRaw.match(
                /^\[(ALERT|RECOVERED)\]\s+account=\d+\s+service=[^\s]+\s+metric=([^\s]+)\s+percent=([\d.]+)%\s+threshold=([\d.]+)%$/i
            );
            if (matched) {
                const type = matched[1].toUpperCase();
                const metricKey = this.escapeHtml(matched[2]);
                const percent = Number(matched[3]);
                const threshold = Number(matched[4]);
                if (type === "ALERT") {
                    detail = `指标 ${metricKey} ${percent.toFixed(1)}% ≥ 阈值 ${threshold.toFixed(1)}%`;
                } else {
                    detail = `指标 ${metricKey} 已恢复（阈值 ${threshold.toFixed(1)}%）`;
                }
            }
            let timeText = "";
            try {
                const t = item.created_at != null ? new Date(item.created_at) : null;
                if (t && !Number.isNaN(t.getTime())) {
                    timeText = this.escapeHtml(
                        `${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")} ${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`
                    );
                }
            } catch (e) {
                /* ignore */
            }
            const emoji = this.alertEventEmoji(item.status);
            return `${emoji} <span class="recent-alert-svc">${svc}</span> · ${acc} · ${detail}` + (timeText ? ` <span class="recent-alert-time">${timeText}</span>` : "");
        },
    };
})(window);
