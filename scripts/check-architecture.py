from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "appointment_bot"
GOVERNED_LAYERS = {"core", "db", "reservation_engine", "services", "worker"}
ALLOWED_TARGETS = {
    "core": {"core"},
    "db": {"core", "db"},
    "reservation_engine": {"core", "reservation_engine"},
    "services": {"core", "db", "reservation_engine", "services"},
    "worker": GOVERNED_LAYERS,
}


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def resolve_existing_module(name: str, modules: set[str]) -> str | None:
    candidate = name
    while candidate.startswith("appointment_bot"):
        if candidate in modules:
            return candidate
        if "." not in candidate:
            break
        candidate = candidate.rsplit(".", 1)[0]
    return None


def import_edges(path: Path, source: str, modules: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = source if path.name == "__init__.py" else source.rsplit(".", 1)[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = resolve_existing_module(alias.name, modules)
                if target:
                    targets.add(target)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = f"{'.' * node.level}{node.module or ''}"
                try:
                    base = importlib.util.resolve_name(relative, package)
                except (ImportError, ValueError):
                    continue
            else:
                base = node.module or ""
            if not base.startswith("appointment_bot"):
                continue
            for alias in node.names:
                candidate = base if alias.name == "*" else f"{base}.{alias.name}"
                target = resolve_existing_module(candidate, modules)
                if target:
                    targets.add(target)
    targets.discard(source)
    return targets


def dependency_graph() -> dict[str, set[str]]:
    paths = sorted(SOURCE_ROOT.rglob("*.py"))
    modules_by_path = {path: module_name(path) for path in paths}
    modules = set(modules_by_path.values())
    return {
        source: import_edges(path, source, modules)
        for path, source in modules_by_path.items()
    }


def layer(module: str) -> str | None:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[1] in GOVERNED_LAYERS else None


def inverse_dependencies(graph: dict[str, set[str]]) -> list[list[str]]:
    violations: list[list[str]] = []
    for source, targets in graph.items():
        source_layer = layer(source)
        if not source_layer:
            continue
        for target in targets:
            target_layer = layer(target)
            if target_layer and target_layer not in ALLOWED_TARGETS[source_layer]:
                violations.append([source, target])
    return sorted(violations)


def strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        if len(component) > 1:
            components.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prevent new inverse imports and cycles.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "scripts" / "architecture-baseline.json",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    graph = dependency_graph()
    current = {
        "inverse_dependencies": inverse_dependencies(graph),
        "cycles": strongly_connected_components(graph),
    }
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    report = {
        "status": "pass" if current == baseline else "fail",
        "module_count": len(graph),
        "edge_count": sum(len(targets) for targets in graph.values()),
        "current": current,
        "baseline": baseline,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(f"{json.dumps(report, indent=2)}\n", encoding="utf-8")
    if current != baseline:
        print(json.dumps(report, indent=2))
        print("Architecture baseline drifted: remove obsolete debt or reject new debt.")
        return 1
    print(
        "Architecture guard passed: "
        f"{len(graph)} modules, {len(current['inverse_dependencies'])} exceptions, "
        f"{len(current['cycles'])} cycles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
