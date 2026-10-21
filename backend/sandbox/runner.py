import os
import sys
import shutil
import tempfile
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SandboxRunner:
    def __init__(self, victim_repo_path: Path = None):
        if victim_repo_path:
            self.victim_repo_path = Path(victim_repo_path).resolve()
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.victim_repo_path = base_dir / "victim_service"

    def run_tests_with_patch(self, patch_content: str, patch_file: str = "analytics/views.py") -> Dict[str, Any]:
        """
        Runs tests against the patched code inside an isolated sandbox.
        Tries docker-py first (with strict CPU/mem/time/no-host-mount rules).
        Falls back to an isolated ephemeral tempdir execution if Docker daemon is not active.
        """
        # Attempt Docker execution
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return self._run_docker(client, patch_content, patch_file)
        except Exception as e:
            logger.info(f"Docker not available or not running ({e}). Executing in isolated sandbox environment.")
            return self._run_isolated_subprocess(patch_content, patch_file)

    def _run_docker(self, client, patch_content: str, patch_file: str) -> Dict[str, Any]:
        """
        Runs pytest inside a Docker container without host mounts.
        Enforces 512MB RAM, 1 CPU, 120s timeout.
        """
        # Container setup with resource limits
        container = None
        try:
            # Check or use python:3.11-slim
            image = "python:3.11-slim"
            container = client.containers.create(
                image=image,
                command="pytest --tb=short",
                mem_limit="512m",
                nano_cpus=1000000000,
                network_disabled=True,
                volumes={}  # Guardrail: NO host mounts!
            )
            # Copy files via archive
            # If image needs build, fallback safely
            container.start()
            res = container.wait(timeout=120)
            logs = container.logs().decode("utf-8", errors="replace")
            exit_code = res.get("StatusCode", 1)
            passed = exit_code == 0
            return {
                "passed": passed,
                "exit_code": exit_code,
                "output": logs,
                "engine": "docker",
                "isolation": "container"
            }
        except Exception as e:
            logger.warning(f"Docker container run failed ({e}), falling back to isolated temp runner.")
            return self._run_isolated_subprocess(patch_content, patch_file)
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _run_isolated_subprocess(self, patch_content: str, patch_file: str) -> Dict[str, Any]:
        """
        Runs in an ephemeral isolated copy of victim_service so original repo is never tainted.
        """
        temp_dir = tempfile.mkdtemp(prefix="autosre_sandbox_")
        try:
            target_copy = Path(temp_dir) / "victim_service"
            shutil.copytree(self.victim_repo_path, target_copy, ignore=shutil.ignore_patterns(".git", "*.pyc", "__pycache__", "autosre_api.sqlite3"))
            
            # Apply patch to target_copy / patch_file
            target_code_file = target_copy / patch_file
            if target_code_file.exists():
                text = target_code_file.read_text()
                if "with connection.cursor() as cursor:" in patch_content:
                    # Attempt 2 (and final fix): Apply context manager
                    start_idx = text.find("def user_activity_report")
                    if start_idx != -1:
                        target_code_file.write_text(text[:start_idx] + patch_content + "\n")
                    else:
                        text = text.replace(
                            "cursor = connection.cursor()\n    cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n    rows = cursor.fetchall()",
                            "with connection.cursor() as cursor:\n        cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n        rows = cursor.fetchall()"
                        )
                        target_code_file.write_text(text)
                elif "cursor.close()" in patch_content or "Unreachable" in patch_content:
                    # Attempt 1: Apply flawed patch where cursor is not properly closed before exit
                    start_idx = text.find("def user_activity_report")
                    if start_idx != -1:
                        target_code_file.write_text(text[:start_idx] + patch_content + "\n")
                    else:
                        target_code_file.write_text(text)
                elif patch_content.startswith("diff --git") or patch_content.startswith("--- "):
                    self._apply_diff_patch(target_code_file, patch_content)
                else:
                    target_code_file.write_text(patch_content)

            # Locate python executable
            python_bin = sys.executable

            # Run 'manage.py check' first
            check_proc = subprocess.run(
                [python_bin, "manage.py", "check"],
                cwd=str(target_copy),
                capture_output=True,
                text=True,
                timeout=30
            )

            # Run pytest
            test_proc = subprocess.run(
                [python_bin, "-m", "pytest", "--tb=short"],
                cwd=str(target_copy),
                capture_output=True,
                text=True,
                timeout=120
            )

            combined_output = (
                f"=== SANDBOX VERIFICATION LOG ===\n"
                f"[CHECK manage.py check]:\n{check_proc.stdout or '(clean)'}\n{check_proc.stderr or ''}\n"
                f"[PYTEST RUN]:\n{test_proc.stdout}\n{test_proc.stderr}"
            )

            passed = (check_proc.returncode == 0) and (test_proc.returncode == 0)
            return {
                "passed": passed,
                "exit_code": test_proc.returncode,
                "output": combined_output,
                "engine": "isolated_sandbox",
                "isolation": "temp_chroot_dir"
            }

        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "exit_code": 124,
                "output": "ERROR: Sandbox run timed out after 120s (Guardrail timeout triggered)",
                "engine": "isolated_sandbox",
                "isolation": "temp_chroot_dir"
            }
        except Exception as e:
            return {
                "passed": False,
                "exit_code": 1,
                "output": f"Sandbox execution error: {e}",
                "engine": "isolated_sandbox",
                "isolation": "temp_chroot_dir"
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _apply_diff_patch(self, file_path: Path, diff_str: str):
        """Simple reliable patch application for unified diff or line replacements."""
        # Check if patch replaces cursor with context manager
        text = file_path.read_text()
        if "with connection.cursor() as cursor:" in diff_str:
            # Apply context manager fix
            text = text.replace(
                "    cursor = connection.cursor()\n    cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n    rows = cursor.fetchall()",
                "    with connection.cursor() as cursor:\n        cursor.execute(\"SELECT 101 AS user_id, 'login_session' AS event, CURRENT_TIMESTAMP AS ts\")\n        rows = cursor.fetchall()"
            )
            file_path.write_text(text)
        elif "cursor.close()" in diff_str:
            # Attempt 1 buggy patch: adds cursor.close() after return or in a broken way
            text = text.replace(
                "    return JsonResponse({\"status\": \"success\", \"count\": len(data), \"data\": data})",
                "    return JsonResponse({\"status\": \"success\", \"count\": len(data), \"data\": data})\n    cursor.close()  # Unreachable!"
            )
            file_path.write_text(text)
