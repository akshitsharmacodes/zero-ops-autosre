"""
Context engineering: hand the agent the code it will need up front.

Correlation already knows the suspect file. Instead of letting the agent spend several
slow, token-expensive turns calling read_file, CodeBriefing packs the suspect file and
the small local modules it imports into the task (within a size budget). Language-
neutral for the main file; Python and JS/TS also get their local imports resolved.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

PY_IMPORT = re.compile(r"^\s*from\s+(\.+[\w.]*|[\w.]+)\s+import\s+([\w, ]+)", re.M)
JS_IMPORT = re.compile(r"""^\s*import\s.+?from\s+['"](\.{1,2}/[^'"]+)['"]""", re.M)


class CodeBriefing:
    def __init__(self, workspace, max_chars: int = 7000, max_files: int = 3):
        self.ws = workspace
        self.max_chars = max_chars
        self.max_files = max_files

    def build(self, primary: str) -> list[tuple[str, str]]:
        """[(path, numbered content)] starting with the primary file, within the budget."""
        files: list[tuple[str, str]] = []
        budget = self.max_chars
        for path in [primary, *self._local_imports(primary)]:
            if len(files) >= self.max_files or budget <= 0:
                break
            try:
                text = self.ws.read_file(path)
            except (FileNotFoundError, ValueError, OSError):
                continue
            numbered = "\n".join(f"{n:4d} | {line}" for n, line in enumerate(text.split("\n"), 1))
            if len(numbered) > budget:
                if files:  # helpers that don't fit are skipped; the agent can still read them
                    continue
                numbered = numbered[:budget] + "\n… (truncated; use read_file for the rest)"
            files.append((path, numbered))
            budget -= len(numbered)
        return files

    def render(self, primary: str) -> str:
        return "\n\n".join(f"--- {path} ---\n{body}" for path, body in self.build(primary))

    # -- import resolution ---------------------------------------------------------------
    def _local_imports(self, primary: str) -> list[str]:
        try:
            text = self.ws.read_file(primary)
        except (FileNotFoundError, ValueError, OSError):
            return []
        here = PurePosixPath(primary).parent
        found: list[str] = []
        if primary.endswith(".py"):
            for module, names in PY_IMPORT.findall(text):
                found += self._python_candidates(here, module, [n.strip() for n in names.split(",")])
        elif primary.endswith((".js", ".ts", ".jsx", ".tsx", ".mjs")):
            for rel in JS_IMPORT.findall(text):
                base = (here / rel).as_posix()
                found += [base + ext for ext in ("", ".ts", ".js", ".tsx", ".jsx", "/index.ts", "/index.js")]
        seen, result = set(), []
        for path in found:
            norm = str(PurePosixPath(path))
            if norm not in seen and norm != primary and self.ws.exists(norm) and self._is_file(norm):
                seen.add(norm)
                result.append(norm)
        return result

    def _python_candidates(self, here: PurePosixPath, module: str, names: list[str]) -> list[str]:
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            base = here
            for _ in range(dots - 1):
                base = base.parent
            rest = module.lstrip(".")
            pkg = base / rest.replace(".", "/") if rest else base
        else:
            pkg = PurePosixPath(module.replace(".", "/"))
        cands = [f"{pkg.as_posix()}.py"]
        cands += [f"{(pkg / n).as_posix()}.py" for n in names if n and n != "*"]  # "from . import pool"
        return cands

    def _is_file(self, path: str) -> bool:
        try:
            return self.ws.resolve(path).is_file()
        except ValueError:
            return False
