"""Build, test and remove only a newly named disposable local Compose project."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = "ss-r5-e2e-" + uuid4().hex[:12]
    env = {**os.environ, "COMPOSE_PROJECT_NAME": project,
           "E2E_COMPOSE_PROJECT": project, "ALLOW_DISPOSABLE_E2E": "1"}
    compose = ["docker", "compose", "-p", project]

    def run(command, cwd=ROOT, timeout=600):
        print("$ " + subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout)

    # A unique name is not permission to remove an existing project.
    for resource, args in (("ps", ["-aq"]), ("volume", ["ls", "-q"]), ("network", ["ls", "-q"])):
        found = subprocess.check_output(
            ["docker", resource, *args, "--filter", f"label=com.docker.compose.project={project}"],
            text=True, env=env, timeout=30,
        ).strip()
        if found:
            raise SystemExit("Project name is already in use. No resources changed.")
    print(f"Disposable E2E project: {project}", flush=True)
    try:
        run([*compose, "config", "--quiet"])
        run([*compose, "build"])
        run([*compose, "up", "-d", "--wait", "--wait-timeout", "180"], timeout=240)
        run([sys.executable, "scripts/smoke_compose.py"])
        run(["npm.cmd" if os.name == "nt" else "npm", "run", "test:e2e"], cwd=ROOT / "frontend", timeout=240)
        run([*compose, "ps", "-a"])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        subprocess.run([*compose, "logs", "--no-color", "--tail", "100"], cwd=ROOT, env=env, timeout=30)
        raise
    finally:
        run([*compose, "down", "--volumes", "--remove-orphans"], timeout=60)


if __name__ == "__main__":
    main()
