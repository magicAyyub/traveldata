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

    if source == "opentripmap" and not __import__("traveldata.config", fromlist=["settings"]).settings.opentripmap_api_key:
        typer.echo("warning: TRAVELDATA_OPENTRIPMAP_API_KEY is empty — OTM will return nothing", err=True)

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
def enrich(
    limit: int = typer.Option(0, help="cap POIs (0 = all unenriched)"),
    refresh: bool = typer.Option(False, help="re-enrich already-enriched POIs"),
    pageviews: bool = typer.Option(True, "--pageviews/--no-pageviews"),
) -> None:
    """Enrich POIs with Wikidata content + Wikipedia pageviews, then re-score."""
    from .enrich import run_enrich
    s = run_enrich(limit=limit or None, with_pageviews=pageviews, refresh=refresh)
    typer.echo(f"pois={s['pois']} wikidata_hits={s['wikidata_hits']} pageviews={s['pageviews']}")

@app.command()
def top(
    metric: str = typer.Option("activity_score",
                               help="hidden_gem_score|activity_score|content_richness|popularity"),
    limit: int = typer.Option(15),
) -> None:
    """Show top POIs by a score, with their real contributing sources."""
    from sqlalchemy import desc, func, select
    from ..db.base import get_sessionmaker
    from ..db.models import Poi, PoiScore, SourceRecord

    valid = {"hidden_gem_score", "activity_score", "content_richness", "popularity"}
    if metric not in valid:
        raise typer.BadParameter(f"metric must be one of {sorted(valid)}")
    col = getattr(PoiScore, metric)

    src_agg = (select(SourceRecord.poi_id,
                      func.array_agg(func.distinct(SourceRecord.source)).label("srcs"))
               .group_by(SourceRecord.poi_id).subquery())

    Session = get_sessionmaker()
    with Session() as s:
        rows = s.execute(
            select(Poi.canonical_name, col, Poi.categories, src_agg.c.srcs)
            .join(PoiScore, PoiScore.poi_id == Poi.id)
            .outerjoin(src_agg, src_agg.c.poi_id == Poi.id)
            .order_by(desc(col)).limit(limit)
        ).all()
    for name, val, cats, srcs in rows:
        typer.echo(f"{(name or '')[:36]:36s} {metric}={(val or 0):.2f} "
                   f"src={','.join(srcs or [])} cats={','.join(cats or [])}")

@app.command()
def serve(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8000),
          reload: bool = typer.Option(False)) -> None:
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run("traveldata.api.main:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    app()