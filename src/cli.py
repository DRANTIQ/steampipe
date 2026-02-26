"""Optional CLI entrypoint."""
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        from src.workers.execution_worker import run_worker_loop
        run_worker_loop()
    elif len(sys.argv) > 1 and sys.argv[1] == "scheduler":
        from src.scheduler.cron_scheduler import run_scheduler
        run_scheduler()
    else:
        import uvicorn
        uvicorn.run("src.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
