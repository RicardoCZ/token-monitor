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
            return {
                used,
                total,
                remain,
                percent,
                expiresAt: expiresAtRaw ? String(expiresAtRaw) : "-",
                resetHours: this.getNumberValue(pageInfo.resetHours ?? pageInfo.reset_hours),
                resetMinutes: this.getNumberValue(pageInfo.resetMinutes ?? pageInfo.reset_minutes),
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
    };
})(window);
