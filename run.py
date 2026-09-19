# -*- coding: utf-8 -*-
"""本地启动 100 Lives：

    python run.py            # http://127.0.0.1:8000
    python run.py --mock     # 离线 Mock（不需要任何密钥）
"""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="100 Lives —— 100 个平行人生模拟器")
    parser.add_argument("--host", default=None, help="监听地址（默认取 .env 的 HOST）")
    parser.add_argument("--port", type=int, default=None, help="端口（默认取 .env 的 PORT）")
    parser.add_argument("--mock", action="store_true", help="强制使用离线 Mock LLM")
    args = parser.parse_args()

    if args.mock:
        import os
        os.environ["LLM_MOCK"] = "1"

    import uvicorn

    from app.config import settings

    host = args.host or settings.host
    port = args.port or settings.port

    print(f"\n  100 Lives · http://{host}:{port}\n")
    uvicorn.run("app.main:app", host=host, port=port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    main()