/**
 * 监控看板 — 共享状态（api.html）
 *
 * 脚本加载顺序（须严格遵守）：
 *   1. api-dashboard-state.js  （本文件 → window.TMD）
 *   2. api-dashboard-core.js   （工具与缓存 → window.TMDCore，依赖 TMD）
 *   3. api-dashboard-app.js    （业务与入口 → window.TMDApp，依赖 TMD + TMDCore）
 */
(function (w) {
    w.TMD = {
        API_BASE: w.location.origin,
        CURRENT_PAGE: (w.location.pathname.split("/").pop() || "api.html").toLowerCase(),
        currentUser: null,
        authToken: localStorage.getItem("token"),
        serviceRegistry: [],
        serviceDataCache: {},
        /** service_id -> account id（用于历史趋势小图） */
        serviceAccountIds: {},
        isRefreshing: false,
        DASHBOARD_CACHE_KEY: "token-monitor:api-dashboard-cache:v1",
    };
})(window);
