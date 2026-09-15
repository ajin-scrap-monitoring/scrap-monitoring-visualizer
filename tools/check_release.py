import argparse
import ast
import re
import subprocess
import tomllib
from pathlib import Path


def resolve_commit(root: Path, revision: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
        cwd=root,
        text=True,
    ).strip()


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as source:
        pyproject_version = tomllib.load(source)["project"]["version"]
    module = ast.parse(
        (root / "src/scrap_monitoring_visualizer/__init__.py").read_text(
            encoding="utf-8"
        )
    )
    module_version: str | None = None
    for statement in module.body:
        if (
            isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in statement.targets
            )
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            module_version = statement.value.value
            break
    if module_version is None:
        raise ValueError("Package __version__ is missing")
    with (root / "edge-bridge/Cargo.toml").open("rb") as source:
        edge_bridge_version = tomllib.load(source)["package"]["version"]
    if len({pyproject_version, module_version, edge_bridge_version}) != 1:
        raise ValueError("Package version declarations do not match")
    return str(pyproject_version)


def validate_release(root: Path, tag: str, revision: str) -> str:
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is None:
        raise ValueError("Release tag must have the form vMAJOR.MINOR.PATCH")
    commit = resolve_commit(root, revision)
    if resolve_commit(root, f"refs/tags/{tag}") != commit:
        raise ValueError("Release tag does not identify the supplied commit")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "refs/remotes/origin/main"],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Release commit must be part of origin/main")
    version = tag[1:]
    if project_version(root) != version:
        raise ValueError("Release tag does not match the package version")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the release tag and main ancestry."
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    version = validate_release(Path.cwd(), args.tag, args.revision)
    print(f"OK: release target {version}")


if __name__ == "__main__":
    main()
