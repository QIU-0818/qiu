#!/usr/bin/env python3
"""Parametric ANSYS Fluent solution runner.

This script provides a small, editable template for running the same Fluent
solution setup over a matrix of input parameters. It is designed to work in two
modes:

* ``--dry-run``: generate Fluent journal files without launching Fluent. This is
  useful on machines that do not have ANSYS installed or when reviewing the
  generated commands before submitting jobs.
* normal mode: launch Fluent through PyFluent (``ansys.fluent.core``), replay the
  generated journal, and save a case/data file for each design point.

Example:
    python fluent_parametric_solution.py --config examples/parameters.json --dry-run
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class DesignPoint:
    """One parametric Fluent run."""

    name: str
    values: dict[str, Any]


def _slug(value: str) -> str:
    """Return a filesystem-safe identifier."""

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def load_config(path: Path) -> dict[str, Any]:
    """Load a JSON configuration file.

    JSON is intentionally used so the script runs with the Python standard
    library. If your team prefers YAML, convert the sample file directly; the
    schema is simple and documented in ``README.md``.
    """

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def expand_design_points(config: dict[str, Any]) -> list[DesignPoint]:
    """Expand explicit design points or a Cartesian parameter matrix."""

    if "design_points" in config:
        points = []
        for index, point in enumerate(config["design_points"], start=1):
            values = dict(point.get("values", point))
            name = point.get("name") or f"dp{index:03d}_" + _slug(
                "_".join(f"{key}-{value}" for key, value in values.items())
            )
            points.append(DesignPoint(name=_slug(name), values=values))
        return points

    matrix = config.get("parameters", {})
    if not matrix:
        raise ValueError("Config must define either 'design_points' or 'parameters'.")

    keys = list(matrix)
    points = []
    for index, combination in enumerate(itertools.product(*(matrix[key] for key in keys)), start=1):
        values = dict(zip(keys, combination, strict=True))
        name = f"dp{index:03d}_" + _slug("_".join(f"{key}-{value}" for key, value in values.items()))
        points.append(DesignPoint(name=name, values=values))
    return points


def fluent_literal(value: Any) -> str:
    """Convert a Python value into a conservative Fluent TUI literal."""

    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    return shlex.quote(str(value))


def render_journal(config: dict[str, Any], point: DesignPoint, output_dir: Path) -> str:
    """Render a Fluent journal for one design point."""

    case_file = config.get("case_file")
    if not case_file:
        raise ValueError("Config must define 'case_file'.")

    commands: list[str] = [
        f'/file/read-case {fluent_literal(case_file)}',
        f'; Design point: {point.name}',
    ]

    named_expressions = config.get("named_expressions", {})
    for expression_name, parameter_name in named_expressions.items():
        if parameter_name not in point.values:
            raise KeyError(f"Missing parameter '{parameter_name}' for expression '{expression_name}'.")
        commands.append(
            "/define/named-expressions/edit "
            f"{fluent_literal(expression_name)} definition {fluent_literal(point.values[parameter_name])} quit"
        )

    boundary_conditions = config.get("boundary_conditions", {})
    for zone_name, zone_settings in boundary_conditions.items():
        for setting_name, parameter_name in zone_settings.items():
            if parameter_name not in point.values:
                raise KeyError(f"Missing parameter '{parameter_name}' for boundary '{zone_name}.{setting_name}'.")
            commands.append(
                "; Update boundary condition "
                f"{zone_name}.{setting_name} = {point.values[parameter_name]}"
            )
            commands.append(
                f"/define/boundary-conditions/set/{zone_name} {setting_name} "
                f"{fluent_literal(point.values[parameter_name])}"
            )

    solution = config.get("solution", {})
    if solution.get("initialize", True):
        commands.append("/solve/initialize/hyb-initialization")
    if "iterations" in solution:
        commands.append(f"/solve/iterate {int(solution['iterations'])}")

    reports = config.get("reports", [])
    for report in reports:
        commands.append(f"/report/surface-integrals/{report}")

    case_data = output_dir / point.name / f"{point.name}.cas.h5"
    commands.extend(
        [
            f"/file/write-case-data {fluent_literal(case_data)}",
            "/exit yes",
        ]
    )
    return "\n".join(commands) + "\n"


def write_manifest(points: Iterable[DesignPoint], output_dir: Path) -> None:
    """Write a CSV manifest to make post-processing easier."""

    points = list(points)
    if not points:
        return
    keys = sorted({key for point in points for key in point.values})
    manifest = output_dir / "design_points.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", *keys])
        writer.writeheader()
        for point in points:
            writer.writerow({"name": point.name, **point.values})


def run_fluent_journal(journal_path: Path, config: dict[str, Any]) -> None:
    """Launch Fluent through PyFluent and replay a journal file."""

    import ansys.fluent.core as pyfluent

    launch_options = config.get("launch", {})
    session = pyfluent.launch_fluent(**launch_options)
    try:
        session.tui.file.read_journal(str(journal_path))
    finally:
        session.exit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or generate Fluent parametric solution journals.")
    parser.add_argument("--config", type=Path, required=True, help="Path to the JSON parameter configuration.")
    parser.add_argument("--output-dir", type=Path, default=Path("runs"), help="Directory for journals and results.")
    parser.add_argument("--dry-run", action="store_true", help="Only generate journals; do not launch Fluent.")
    args = parser.parse_args()

    config = load_config(args.config)
    points = expand_design_points(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for point in points:
        point_dir = args.output_dir / point.name
        point_dir.mkdir(parents=True, exist_ok=True)
        journal_path = point_dir / f"{point.name}.jou"
        journal_path.write_text(render_journal(config, point, args.output_dir), encoding="utf-8")
        print(f"wrote {journal_path}")
        if not args.dry_run:
            run_fluent_journal(journal_path, config)

    write_manifest(points, args.output_dir)
    print(f"prepared {len(points)} design point(s) in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
