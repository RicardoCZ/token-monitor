/**
 * 监控看板 — 纯工具、sessionStorage 缓存、指标解析（api.html）
 *
 * 依赖：先加载 api-dashboard-state.js（window.TMD）。
 * 后继：api-dashboard-app.js
 */
(function (w) {
    const S = w.TMD;

    w.TMDCore = {
        escapeHtml(text) {
            const div = document.createElement("div");
            div.textContent = text == null ? "" : String(text);
            return div.innerHTML;
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

        /** 简单 SVG 折线（0–100 竖直域），用于监控卡片 7d 趋势 */
        buildSparklineSvg(percentSeries, strokeColor = "#6f88ff") {
            const vals = Array.isArray(percentSeries)
                ? percentSeries.map((v) => this.getNumberValue(v)).filter((n) => Number.isFinite(n))
                : [];
            const w = 120;
            const h = 36;
            const padX = 2;
            const padY = 3;
            if (vals.length < 2) {
                return `<svg class="sparkline-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><text x="4" y="22" fill="#666" font-size="9">暂无足够数据</text></svg>`;
            }
            let minV = Math.min(...vals);
            let maxV = Math.max(...vals);
            if (maxV - minV < 1e-6) {
                minV = Math.max(0, minV - 5);
                maxV = Math.min(100, maxV + 5);
            }
            const span = Math.max(1e-6, maxV - minV);
            const innerW = w - padX * 2;
            const innerH = h - padY * 2;
            const pts = vals.map((v, i) => {
                const x = padX + (i / (vals.length - 1)) * innerW;
                const y = padY + (1 - (v - minV) / span) * innerH;
                return `${x.toFixed(2)},${y.toFixed(2)}`;
            });
            const line = pts.join(" ");
            const bottom = h - padY;
            const area = `${padX},${bottom} ${line} ${w - padX},${bottom}`;
            const safeStroke = String(strokeColor || "#6f88ff").replace(/[^#0-9a-fA-F]/g, "") || "#6f88ff";
            return (
                `<svg class="sparkline-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
                `<polygon points="${area}" fill="${safeStroke}" fill-opacity="0.12" />` +
                `<polyline points="${line}" fill="none" stroke="${safeStroke}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />` +
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
