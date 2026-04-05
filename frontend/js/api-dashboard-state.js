/**
 * 共享前端状态（window.TMD）
 *
 * 加载本文件 + api-dashboard-core.js 的页面：api.html，以及 accounts / admin / history / setup 等
 * （共用 TMDCore：escapeHtml、extractApiErrorMessage、指标与数字工具等）。
 *
 * 仅监控看板完整链路须再加载 ui-shared.js 与 api-dashboard-app.js：
 *   state → core → ui-shared → app
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
