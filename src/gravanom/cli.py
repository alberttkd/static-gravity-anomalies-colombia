"""Command-line interface: ``gravanom ingest/qc/reduce/grid/validate/report/run/export-static-demo``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated, Any

import typer

from gravanom.config import PipelineConfig, load_yaml

app = typer.Typer(add_completion=False, help="Static gravity anomalies: reduction, QC, gridding and products.")

DatasetOpt = Annotated[str, typer.Option("--dataset", "-d", help="synthetic | private")]
ConfigOpt = Annotated[
    Path | None,
    typer.Option("--config", "-c", help="YAML with reduction/gridding/uncertainty/density sections"),
]
OutOpt = Annotated[
    Path | None,
    typer.Option("--artifacts", help="Artifacts root (default: $GRAVANOM_ARTIFACTS_DIR or ./artifacts)"),
]


def _config(path: Path | None) -> PipelineConfig:
    return PipelineConfig.model_validate(load_yaml(path)) if path else PipelineConfig()


def _logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _echo_json(obj: Any) -> None:
    from gravanom.io.writers import to_jsonable

    typer.echo(json.dumps(to_jsonable(obj), indent=2, ensure_ascii=True))


@app.command()
def ingest(
    dataset: DatasetOpt = "synthetic", out: Annotated[Path, typer.Option("--out")] = Path("stations.parquet")
) -> None:
    """S1-S2: read sources, harmonize, write a station GeoParquet (pre-QC)."""
    from gravanom.harmonize import harmonize
    from gravanom.io.writers import write_geoparquet
    from gravanom.pipeline import load_dataset

    ds = load_dataset(dataset)
    cat, log = harmonize(ds.records)
    write_geoparquet(cat, out)
    _echo_json({k: v for k, v in log.items() if k != "merged_groups"})


@app.command()
def qc(dataset: DatasetOpt = "synthetic", out: Annotated[Path, typer.Option("--out")] = Path("qc_report.json")) -> None:
    """S3: QC flags and report."""
    from gravanom.io.writers import write_json
    from gravanom.pipeline import build_catalogue, load_dataset

    _, report = build_catalogue(load_dataset(dataset))
    write_json(report, out)
    _echo_json(report.flag_counts)


@app.command()
def reduce(
    dataset: DatasetOpt = "synthetic",
    config: ConfigOpt = None,
    out: Annotated[Path, typer.Option("--out")] = Path("anomalies.parquet"),
) -> None:
    """S4-S5: anomalies and station σ."""
    from gravanom.pipeline import build_catalogue, load_dataset, reduce_stations

    cfg = _config(config)
    cat, _ = build_catalogue(load_dataset(dataset))
    _, table = reduce_stations(cat, cfg)
    table.to_parquet(out, index=False)
    _echo_json(table[["faa_mgal", "sba_mgal", "cba_mgal"]].describe().round(3).to_dict())


@app.command()
def run(
    dataset: DatasetOpt = "synthetic",
    config: ConfigOpt = None,
    artifacts: OutOpt = None,
    validation: Annotated[str, typer.Option(help="full | quick | none")] = "full",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = True,
) -> None:
    """S1-S9: the complete pipeline into ``artifacts/<dataset>/<run_id>/``."""
    from gravanom.pipeline import run_pipeline

    _logging(verbose)
    if validation not in ("full", "quick", "none"):
        raise typer.BadParameter("validation must be full, quick or none")
    run_dir = run_pipeline(dataset, _config(config), artifacts, validation)  # type: ignore[arg-type]
    typer.echo(str(run_dir))


@app.command()
def grid(dataset: DatasetOpt = "synthetic", config: ConfigOpt = None, artifacts: OutOpt = None) -> None:
    """S1-S9 without the nested-CV comparison (fast gridding only)."""
    run(dataset, config, artifacts, "none")


@app.command()
def validate(dataset: DatasetOpt = "synthetic", config: ConfigOpt = None, artifacts: OutOpt = None) -> None:
    """S1-S9 with the full nested-CV method comparison and sensitivities."""
    run(dataset, config, artifacts, "full")


@app.command()
def report(run_dir: Annotated[Path, typer.Argument(help="A run directory")]) -> None:
    """Print a summary of a run's key results."""

    def load(name: str) -> Any:
        p = run_dir / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    sel, sens, dens, unc = (
        load("selection.json"),
        load("sensitivity.json"),
        load("density_report.json"),
        load("uncertainty_report.json"),
    )
    _echo_json(
        {
            "selection": sel,
            "masks": sens and sens.get("masks"),
            "cell_size": sens and sens.get("cell_size"),
            "density": dens and {k: dens[k] for k in ("nettleton", "parasnis", "h5")},
            "uncertainty": unc and unc.get("per_anomaly"),
        }
    )


@app.command("export-static-demo")
def export_static_demo(
    out: Annotated[Path, typer.Option("--out")] = Path("frontend/public/demo"),
    run_dir: Annotated[Path | None, typer.Option("--run-dir", help="Existing synthetic run (default: new run)")] = None,
    artifacts: OutOpt = None,
) -> None:
    """Export precomputed JSON/PNG/GeoJSON of a *synthetic* run for the static web demo."""
    from gravanom.demo import export_demo
    from gravanom.pipeline import run_pipeline

    _logging(True)
    rd = run_dir or run_pipeline("synthetic", PipelineConfig(), artifacts, "full")
    typer.echo(str(export_demo(rd, out)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
