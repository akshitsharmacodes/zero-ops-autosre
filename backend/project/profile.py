"""
Project profile: how to install and test the target project, whatever its tech stack.

Read from `.autosre.yml` in the repo when present; otherwise detected from well-known
files (requirements.txt / pyproject.toml, package.json, go.mod, pom.xml).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

CONFIG_FILE = ".autosre.yml"


class ProfileError(ValueError):
    pass


@dataclass
class ProjectProfile:
    name: str
    language: str
    base_image: str
    install: str
    test: str
    dependency_files: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    test_single: str | None = None  # "{path}" = one test file
    tests_dir: str = "tests"
    test_file_glob: str = "tests/test_*"
    source: str = "detected"  # file | detected

    def as_dict(self) -> dict:
        return asdict(self)

    def image_tag(self, repo_dir: Path) -> str:
        """Sandbox image name. Changes whenever the base image, install command or dependency files change."""
        h = hashlib.sha256()
        h.update(f"{self.base_image}\n{self.install}\n".encode())
        for rel in sorted(self.dependency_files):
            p = Path(repo_dir) / rel
            if p.is_file():
                h.update(rel.encode() + b"\0" + p.read_bytes())
        slug = re.sub(r"[^a-z0-9-]+", "-", self.name.lower()).strip("-") or "project"
        return f"autosre-sandbox-{slug}:{h.hexdigest()[:12]}"

    def single_test_command(self, path: str) -> str | None:
        return self.test_single.replace("{path}", path) if self.test_single else None


def load_profile(repo_dir: str | Path) -> ProjectProfile:
    repo = Path(repo_dir)
    cfg = repo / CONFIG_FILE
    if cfg.is_file():
        return _from_config(cfg, repo)
    detected = detect_profile(repo)
    if not detected:
        raise ProfileError(
            f"Could not tell how to build/test this project. Add a {CONFIG_FILE} file "
            "with at least: language, base_image, install, test."
        )
    return detected


def _from_config(path: Path, repo: Path) -> ProjectProfile:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ProfileError(f"{CONFIG_FILE} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{CONFIG_FILE} must be a mapping")

    defaults = detect_profile(repo)
    base = defaults.as_dict() if defaults else {}
    merged = {**base, **{k: v for k, v in data.items() if v is not None}}
    merged.setdefault("name", repo.name)
    missing = [k for k in ("language", "base_image", "install", "test") if not merged.get(k)]
    if missing:
        raise ProfileError(f"{CONFIG_FILE} is missing: {', '.join(missing)}")
    if isinstance(merged.get("checks"), str):
        merged["checks"] = [merged["checks"]]
    allowed = set(ProjectProfile.__dataclass_fields__)
    unknown = set(merged) - allowed
    if unknown:
        raise ProfileError(f"{CONFIG_FILE} has unknown keys: {', '.join(sorted(unknown))}")
    merged["source"] = "file"
    return ProjectProfile(**merged)


def detect_profile(repo: Path) -> ProjectProfile | None:
    for detector in (_python, _node, _go, _maven):
        profile = detector(repo)
        if profile:
            return profile
    return None


def _python(repo: Path) -> ProjectProfile | None:
    if (repo / "requirements.txt").is_file():
        deps, install = ["requirements.txt"], "pip install --no-cache-dir -r requirements.txt"
    elif (repo / "pyproject.toml").is_file():
        deps, install = ["pyproject.toml"], "pip install --no-cache-dir . pytest"
    else:
        return None
    checks = ["python manage.py check"] if (repo / "manage.py").is_file() else []
    return ProjectProfile(
        name=repo.name, language="python", base_image="python:3.11-slim", install=install,
        dependency_files=deps, checks=checks, test="python -m pytest",
        test_single="python -m pytest {path}", tests_dir="tests", test_file_glob="tests/test_*.py",
    )


def _node(repo: Path) -> ProjectProfile | None:
    pkg = repo / "package.json"
    if not pkg.is_file():
        return None
    try:
        scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
    except json.JSONDecodeError:
        scripts = {}
    lock = "package-lock.json" if (repo / "package-lock.json").is_file() else None
    return ProjectProfile(
        name=repo.name, language="node", base_image="node:20-slim",
        install="npm ci" if lock else "npm install",
        dependency_files=["package.json"] + ([lock] if lock else []),
        checks=["npm run lint"] if "lint" in scripts else [],
        test="npm test", test_single="npm test -- {path}",
        tests_dir="test", test_file_glob="**/*.test.*",
    )


def _go(repo: Path) -> ProjectProfile | None:
    if not (repo / "go.mod").is_file():
        return None
    deps = ["go.mod"] + (["go.sum"] if (repo / "go.sum").is_file() else [])
    return ProjectProfile(
        name=repo.name, language="go", base_image="golang:1.22", install="go mod download",
        dependency_files=deps, checks=["go vet ./..."], test="go test ./...", test_single=None,
        tests_dir=".", test_file_glob="**/*_test.go",
    )


def _maven(repo: Path) -> ProjectProfile | None:
    if not (repo / "pom.xml").is_file():
        return None
    return ProjectProfile(
        name=repo.name, language="java", base_image="maven:3.9-eclipse-temurin-21",
        install="mvn -q -B dependency:go-offline", dependency_files=["pom.xml"],
        test="mvn -q -B -o test", test_single=None,
        tests_dir="src/test/java", test_file_glob="src/test/java/**/*Test.java",
    )
