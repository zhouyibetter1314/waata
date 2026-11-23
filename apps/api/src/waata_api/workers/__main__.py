"""Start the WAATA C6 worker process."""

import asyncio
import logging
import signal
from contextlib import suppress

from waata_api.infrastructure.config import Settings

from .runtime import run_worker


async def _run() -> None:
    # stop 是启动入口和 Worker 共享的停止信号。set() 会唤醒等待 stop.wait() 的任务。
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    # Ctrl+C 或进程终止信号到来时，事件循环调用 stop.set()，让 Worker 开始退出流程。
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    # run_worker 会一直运行到收到停止信号或发生异常。它等待数据库等操作时，
    # 事件循环可以运行同进程的其他任务，例如正在执行的测试和租约心跳。
    await run_worker(Settings.from_env(), stop)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        # asyncio.run() 创建事件循环，等待 _run() 结束，再关闭循环。
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except (ValueError, RuntimeError):
        logging.getLogger(__name__).error(
            "Worker startup failed; check the model, deployment and database configuration"
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
