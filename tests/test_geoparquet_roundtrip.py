"""Contract: geometry built in Polars survives DuckDB spatial -> GeoParquet -> Polars/DuckDB unchanged, Z included.

The DuckDB spatial extension is fetched on first use, so the first run needs network access.
"""
import json

import duckdb
import polars as pl
import polars_st as st
import pyarrow.parquet as pq

WKT = {"point": "POINT Z (1 2 3)", "footprint": "POLYGON ((0 0, 4 0, 4 3, 0 3, 0 0))"}


def test_geoparquet_roundtrip(tmp_path):
    path = tmp_path / "objects.parquet"
    source = st.GeoDataFrame({"object_id": list(WKT), "geometry": list(WKT.values())})
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.register("src", source.select("object_id", st.geom().st.to_wkb().alias("wkb")).to_arrow())
    con.execute(f"COPY (SELECT object_id, ST_GeomFromWKB(wkb) AS geometry FROM src) TO '{path}' (FORMAT parquet)")

    geo = json.loads(pq.read_schema(path).metadata[b"geo"])
    assert geo["primary_column"] == "geometry"
    assert geo["columns"]["geometry"]["encoding"] == "WKB"

    polars_back = pl.read_parquet(path).select("object_id", st.from_wkb("geometry").st.to_wkt().alias("wkt"))
    assert dict(polars_back.iter_rows()) == WKT

    duckdb_back = con.execute(f"SELECT object_id, ST_AsText(geometry), ST_Area(geometry) FROM '{path}'").fetchall()
    assert {oid: (wkt, area) for oid, wkt, area in duckdb_back} == {
        "point": (WKT["point"], 0.0),
        "footprint": (WKT["footprint"], 12.0),
    }
