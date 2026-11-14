"""
Database Migration CLI Utility for TaskForge AI.
Usage:
    python migrate.py upgrade
    python migrate.py downgrade
    python migrate.py stamp
    python migrate.py current
"""
import sys
from alembic.config import Config
from alembic import command
import os

def run_migrations():
    alembic_ini_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)

    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    target = sys.argv[2] if len(sys.argv) > 2 else "head"

    print(f"[TaskForge Migration] Executing '{action}' targeting '{target}'...")

    if action == "upgrade":
        command.upgrade(alembic_cfg, target)
        print("[TaskForge Migration] Database successfully migrated to:", target)
    elif action == "downgrade":
        command.downgrade(alembic_cfg, target)
        print("[TaskForge Migration] Database downgraded to:", target)
    elif action == "current":
        command.current(alembic_cfg)
    elif action == "stamp":
        command.stamp(alembic_cfg, target)
        print("[TaskForge Migration] Stamped database at:", target)
    else:
        print(f"Unknown action: {action}. Supported: upgrade, downgrade, current, stamp")

if __name__ == "__main__":
    run_migrations()

