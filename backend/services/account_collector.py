"""
账号用量采集器（P2-2）
- 复用单账号采集逻辑（供 API 手动 sync 与自动调度共用）
- 提供后台定时调度器（并发限制 + 重试 + 基础观测）
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.encryption import decrypt_data
from models.db_models import Account, Service, UsageSnapshot
from services.minimax_service import MiniMaxService
from services.xunfei_service import XunFeiService
from services.alerting_service import evaluate_alert_for_snapshot
from utils.usage_snapshot_writer import persist_usage_collection


async def _mark_collect_failed(db: AsyncSession, account: Account, message: str) -> None:
    account.last_collect_status = "failed"
    account.last_collect_error = message
    await db.commit()


async def _fetch_usage_data(account: Account, cookies: str) -> dict:
    if account.service_id == "minimax":
        service = MiniMaxService()
        return await service.get_usage(cookies=cookies, group_id=account.group_id)
    if account.service_id == "xfyun":
        service = XunFeiService()
        return await service.get_usage(cookies=cookies)
    raise ValueError(f"不支持的服务类型: {account.service_id}")


async def collect_account_usage(
    db: AsyncSession,
    account: Account,
    *,
    retry_attempts: int = 2,
    retry_delay_seconds: float = 1.0,
) -> dict:
    """
    采集并落库单个账号（usage_snapshots 单轨）。
    retry_attempts 表示总尝试次数（>=1）。
    """
    if not account.cookies_encrypted:
        await _mark_collect_failed(db, account, "账号未配置 Cookie")
        raise ValueError("账号未配置 Cookie")

    cookies = decrypt_data(account.cookies_encrypted)
    if not cookies:
        await _mark_collect_failed(db, account, "Cookie 解密失败")
        raise ValueError("Cookie 解密失败")

    attempts = max(1, int(retry_attempts))
    last_error: Exception | None = None

    for idx in range(attempts):
        try:
            data = await _fetch_usage_data(account, cookies)
            page_info = await persist_usage_collection(db, account, data)
            latest_snapshot_result = await db.execute(
                select(UsageSnapshot)
                .where(UsageSnapshot.account_id == account.id)
                .order_by(UsageSnapshot.collected_at.desc(), UsageSnapshot.id.desc())
                .limit(1)
            )
            latest_snapshot = latest_snapshot_result.scalar_one_or_none()
            if latest_snapshot:
                await evaluate_alert_for_snapshot(db, latest_snapshot)
            return page_info
        except ValueError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            await _mark_collect_failed(db, account, f"采集异常: {exc}")

        if idx < attempts - 1:
            await asyncio.sleep(max(0.0, retry_delay_seconds))

    if last_error is None:
        raise ValueError("采集失败")
    raise ValueError(str(last_error))


class AccountAutoCollector:
    """后台自动采集调度器。"""

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        interval_seconds: int = 300,
        max_concurrency: int = 3,
        retry_attempts: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = max(30, int(interval_seconds))
        self._max_concurrency = max(1, int(max_concurrency))
        self._retry_attempts = max(1, int(retry_attempts))
        self._retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="account-auto-collector")
        print(
            f"✅ 自动采集任务已启动（间隔 {self._interval_seconds}s, 并发 {self._max_concurrency}, 重试 {self._retry_attempts} 次）"
        )

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        print("👋 自动采集任务已停止")

    async def _list_target_account_ids(self) -> list[int]:
        async with self._session_factory() as db:
            result = await db.execute(
                select(Account.id)
                .join(Service, Service.id == Account.service_id)
                .where(Account.is_active.is_(True))
                .where(Account.cookies_encrypted.is_not(None))
                .where(Account.cookies_encrypted != "")
                .where(Service.is_enabled.is_(True))
                .order_by(Account.id.asc())
            )
            return [int(item) for item in result.scalars().all()]

    async def _collect_one(self, account_id: int, sem: asyncio.Semaphore) -> tuple[bool, float, str]:
        async with sem:
            started = time.perf_counter()
            try:
                async with self._session_factory() as db:
                    account = await db.get(Account, account_id)
                    if not account:
                        return False, time.perf_counter() - started, "账号不存在"
                    await collect_account_usage(
                        db,
                        account,
                        retry_attempts=self._retry_attempts,
                        retry_delay_seconds=self._retry_delay_seconds,
                    )
                return True, time.perf_counter() - started, ""
            except Exception as exc:  # noqa: BLE001
                return False, time.perf_counter() - started, str(exc)

    async def _run_cycle(self) -> None:
        cycle_start = time.perf_counter()
        account_ids = await self._list_target_account_ids()
        if not account_ids:
            print("ℹ️ 自动采集本轮跳过：无可采集账号")
            return

        sem = asyncio.Semaphore(self._max_concurrency)
        results = await asyncio.gather(*(self._collect_one(aid, sem) for aid in account_ids))

        success_count = sum(1 for ok, _, _ in results if ok)
        failed = [(cost, err) for ok, cost, err in results if not ok]
        failed_count = len(failed)
        elapsed = time.perf_counter() - cycle_start
        avg_cost = sum(cost for _, cost, _ in results) / len(results) if results else 0.0

        print(
            f"📊 自动采集完成: 账号 {len(account_ids)} 个, 成功 {success_count}, 失败 {failed_count}, "
            f"总耗时 {elapsed:.2f}s, 平均 {avg_cost:.2f}s/账号"
        )
        if failed_count:
            sample_error = failed[0][1]
            print(f"⚠️ 自动采集失败样例: {sample_error}")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            loop_start = time.perf_counter()
            await self._run_cycle()
            spent = time.perf_counter() - loop_start
            wait_seconds = max(0.0, self._interval_seconds - spent)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                continue
