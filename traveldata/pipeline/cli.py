"""traveldata CLI."""
from __future__ import annotations

import typer

from ..connectors import CONNECTORS
from ..score import scorer

app = typer.Typer(help="traveldata pipeline")


@app.command()
def sources() -> None:
    """List available connectors."""
    for name, cls in CONNECTORS.items():
        typer.echo(f"{name:14s} license={cls.license}")


@app.command()
def ingest(
    source: str = typer.Option("opentripmap", help="connector name"),
    lat: float = typer.Option(...),
    lon: float = typer.Option(...),
    radius_m: int = typer.Option(3000),
    limit: int = typer.Option(0, help="cap records (0 = no cap)"),
    persist: bool = typer.Option(True, help="--no-persist for a scored dry-run preview"),
) -> None:
    """Fetch a point's POIs. Default persists raw records; --no-persist previews + scores."""
    if source not in CONNECTORS:
        raise typer.BadParameter(f"unknown source '{source}'. try: {list(CONNECTORS)}")
    conn = CONNECTORS[source]()

    if persist:
        from .ingest import run_ingest
        c = run_ingest(conn, lat, lon, radius_m=radius_m, limit=limit or None)
        typer.echo(
            f"fetched={c['total']} new={c['new']} updated={c['updated']} unchanged={c['unchanged']}"
        )
        return

    # --no-persist: scored dry-run preview (no DB needed)
    shown = 0
    cap = limit or 10
    for unit in conn.discover(lat, lon, radius_m=radius_m):
        for raw in conn.fetch(unit):
            for d in conn.to_drafts(raw):
                s = scorer.score(scorer.PoiFeatures(
                    categories=d.categories, has_coordinates=True,
                    description_len=len(d.short_description or ""), image_count=len(d.images),
                    source_count=1, lang_count=len(d.names),
                    otm_rate=d.importance_raw, osm_present="osm" in d.source_xids,
                ))
                typer.echo(f"{d.canonical_name[:40]:40s} gem={s.hidden_gem_score:.2f} "
                           f"act={s.activity_score:.2f} cats={','.join(d.categories)}")
                shown += 1
                if shown >= cap:
                    raise typer.Exit()


@app.command()
def stats() -> None:
    """Count landed source_records by source."""
    from sqlalchemy import func, select
    from ..db.base import get_sessionmaker
    from ..db.models import SourceRecord

    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            select(SourceRecord.source, func.count()).group_by(SourceRecord.source)
        ).all()
    if not rows:
        typer.echo("(no source_records yet)")
    for src, n in rows:
        typer.echo(f"{src:14s} {n}")


@app.command()
def resolve(
    rebuild: bool = typer.Option(False, help="wipe poi/links/scores and re-resolve all records"),
    max_distance_m: int = typer.Option(80, help="candidate radius for spatial matching"),
    name_threshold: float = typer.Option(0.85, help="0..1 name similarity to accept a match"),
) -> None:
    """Resolve source_records -> canonical POIs, conflate, and score."""
    from .resolve import run_resolve
    s = run_resolve(rebuild=rebuild, max_distance_m=max_distance_m, name_threshold=name_threshold)
    typer.echo(f"records={s['records']} matched={s['matched']} created={s['created']}")


@app.command()
def top(
    metric: str = typer.Option("activity_score",
                               help="hidden_gem_score|activity_score|content_richness|popularity"),
    limit: int = typer.Option(15),
) -> None:
    """Show top POIs by a score, to eyeball results."""
    from sqlalchemy import desc, select
    from ..db.base import get_sessionmaker
    from ..db.models import Poi, PoiScore

    valid = {"hidden_gem_score", "activity_score", "content_richness", "popularity"}
    if metric not in valid:
        raise typer.BadParameter(f"metric must be one of {sorted(valid)}")
    col = getattr(PoiScore, metric)

    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            select(Poi.canonical_name, col, Poi.categories, Poi.source_xids)
            .join(PoiScore, PoiScore.poi_id == Poi.id)
            .order_by(desc(col))
            .limit(limit)
        ).all()
    for name, val, cats, xids in rows:
        typer.echo(f"{(name or '')[:38]:38s} {metric}={val:.2f} "
                   f"src={','.join(xids.keys())} cats={','.join(cats or [])}")


if __name__ == "__main__":
    app()