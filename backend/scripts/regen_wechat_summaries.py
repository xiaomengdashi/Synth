"""一次性重生成存量微信文章摘要（服务器直接运行，逐篇打印进度）。

用法（服务器 backend 目录）：
    /opt/synthai/venv/bin/python scripts/regen_wechat_summaries.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.wechat_summary_regen import progress_snapshot, regenerate_wechat_summaries


async def main() -> int:
    print("开始重生成存量微信文章摘要…")
    result = await regenerate_wechat_summaries()
    print(
        f"完成：共 {result['total']} 篇，"
        f"重生成 {result['ok']}，过短跳过 {result['skipped']}，失败 {result['failed']}"
    )
    return 0 if not result["running"] else 1


if __name__ == "__main__":
    snapshot = asyncio.run(main())
    raise SystemExit(snapshot)
