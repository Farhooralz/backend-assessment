"""Run PostgreSQL 16 and Redis WITHOUT Docker or root (fallback when `docker compose` is not usable).

Usage (through the wrapper, which creates the helper venv on first use):
    scripts/local_infra.sh start     # start both, write ./.env for the tasks
    scripts/local_infra.sh status
    scripts/local_infra.sh stop

PostgreSQL comes from the `pgserver` wheel (real PostgreSQL 16 binaries, unix socket, user
`postgres`, no password). Redis comes from the `redislite` wheel (real redis-server binary).
Data lives in ./.local-infra (git-ignored).
"""

import argparse
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / ".local-infra"
PGDATA = DATA / "pgdata"
REDIS_DIR = DATA / "redis"
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))


def _redis_bin() -> str:
    import redislite

    return redislite.__redis_executable__


def _redis_up() -> bool:
    import redis

    try:
        return bool(redis.Redis(host="127.0.0.1", port=REDIS_PORT, socket_timeout=1).ping())
    except redis.RedisError:
        return False


def start() -> None:
    import pgserver

    DATA.mkdir(exist_ok=True)
    PGDATA.mkdir(exist_ok=True)
    REDIS_DIR.mkdir(exist_ok=True)
    pgserver.get_server(PGDATA, cleanup_mode=None)  # None = keep running after this process exits
    print(f"postgres: up, socket dir {PGDATA}")

    if not _redis_up():
        subprocess.run(
            [
                _redis_bin(),
                "--port", str(REDIS_PORT),
                "--bind", "127.0.0.1",
                "--dir", str(REDIS_DIR),
                "--daemonize", "yes",
                "--save", "",
                "--pidfile", str(REDIS_DIR / "redis.pid"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for _ in range(20):
            if _redis_up():
                break
            time.sleep(0.25)
    print(f"redis: {'up' if _redis_up() else 'FAILED'} on 127.0.0.1:{REDIS_PORT}")

    env = ROOT / ".env"
    env.write_text(
        "# Written by scripts/local_infra.py (local, no Docker). Git-ignored.\n"
        f'POSTGRES_HOST="{PGDATA}"\n'
        "POSTGRES_PORT=\n"
        "POSTGRES_USER=postgres\n"
        "POSTGRES_PASSWORD=\n"
        "POSTGRES_DB=postgres\n"
        "REDIS_HOST=127.0.0.1\n"
        f"REDIS_PORT={REDIS_PORT}\n"
    )
    print(f"wrote {env}. Load it with:  set -a; . ./.env; set +a")


def status() -> None:
    import pgserver

    ready = subprocess.run(
        [str(pgserver._commands.POSTGRES_BIN_PATH / "pg_isready"), "-h", str(PGDATA)],
        capture_output=True,
        text=True,
    )
    print("postgres:", ready.stdout.strip() or ready.stderr.strip())
    print("redis:", "up" if _redis_up() else "down")


def stop() -> None:
    import pgserver
    import redis

    # cleanup_mode="stop" + cleanup() asks pgserver to stop the running server (works as root too)
    pgserver.get_server(PGDATA, cleanup_mode="stop").cleanup()
    try:
        redis.Redis(host="127.0.0.1", port=REDIS_PORT).shutdown(nosave=True)
    except redis.RedisError:
        pass
    print("stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["start", "status", "stop"])
    {"start": start, "status": status, "stop": stop}[parser.parse_args().command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())