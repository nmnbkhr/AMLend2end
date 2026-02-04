"""
Enrichment Loader — Phase B

Load and aggregate ``extra_info.csv`` (or ``edges_enriched_td.csv``)
per party to produce per-entity enrichment features used by the AML
score calculator.

If the enrichment file is missing the module returns an empty DataFrame
so that downstream scoring can still proceed (laundering / geo signals
default to 0).
"""

import logging
from pathlib import Path
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Column-name candidates for transaction id join
_TRAN_ID_CANDIDATES = ["tran_id", "id", "transaction_id", "txn_id"]
_SRC_CANDIDATES = ["src", "source", "from", "sender", "id1"]
_DST_CANDIDATES = ["dst", "target", "to", "receiver", "id2"]

# Enrichment column renames (normalise whatever the CSV provides)
_ENRICHMENT_RENAMES = {
    "is_laundering": "is_laundering",
    "laundering_type": "laundering_type",
    "payment_currency": "payment_currency",
    "received_currency": "received_currency",
    "sender_bank_location": "sender_bank_location",
    "receiver_bank_location": "receiver_bank_location",
}


def _find_col(columns: list, candidates: list) -> str | None:
    """Return the first column name (case-insensitive) matching *candidates*."""
    lower_map = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def _load_enrichment_raw(data_dir: Path) -> pd.DataFrame | None:
    """
    Attempt to load enrichment data from one of the supported files.

    Priority:
      1. ``edges_enriched_td.csv`` — already sampled & joined by notebook 1
      2. ``extra_info.csv`` (full or sampled)

    Returns None if neither file exists.
    """
    enriched_path = data_dir / "edges_enriched_td.csv"
    extra_info_path = data_dir / "extra_info.csv"

    if enriched_path.exists():
        logger.info(f"Loading enrichment from {enriched_path.name}")
        return pd.read_csv(enriched_path)
    if extra_info_path.exists():
        logger.info(f"Loading enrichment from {extra_info_path.name}")
        return pd.read_csv(extra_info_path)

    # Also check the demodata directory (one level up from artifacts data dir)
    project_root = data_dir.parent.parent.parent.parent  # artifacts/runs/<id>/data -> project
    for search_dir in [project_root / "demodata", project_root]:
        candidate = search_dir / "extra_info.csv"
        if candidate.exists():
            logger.info(f"Loading enrichment from {candidate}")
            return pd.read_csv(candidate)

    return None


def load_enrichment(data_dir: Path) -> pd.DataFrame:
    """
    Load and aggregate enrichment data per party.

    Returns a DataFrame indexed by ``party_id`` with columns::

        txn_count, total_amt, laundering_txn_count, laundering_types,
        cross_border_count, cross_currency_count, unique_jurisdictions,
        unique_currencies

    If no enrichment file is found, returns an empty DataFrame with the
    correct columns so downstream merge still works.
    """
    empty = pd.DataFrame(columns=[
        "party_id", "txn_count", "total_amt",
        "laundering_txn_count", "laundering_types",
        "cross_border_count", "cross_currency_count",
        "unique_jurisdictions", "unique_currencies",
    ])

    raw = _load_enrichment_raw(data_dir)
    if raw is None:
        logger.info("No enrichment file found — laundering/geo signals will be 0")
        return empty

    logger.info(f"Enrichment raw rows: {len(raw):,}")
    raw.columns = [c.strip() for c in raw.columns]

    # Detect key columns
    src_col = _find_col(raw.columns, _SRC_CANDIDATES)
    dst_col = _find_col(raw.columns, _DST_CANDIDATES)

    if src_col is None or dst_col is None:
        # Try to join via edges_td.csv using a transaction-id key
        tran_col = _find_col(raw.columns, _TRAN_ID_CANDIDATES)
        if tran_col is None:
            logger.warning(
                f"Cannot determine party from enrichment columns: {raw.columns.tolist()}. "
                "Need src/dst columns or a tran_id to join with edges."
            )
            return empty
        raw, src_col, dst_col = _join_with_edges(raw, tran_col, data_dir)
        if src_col is None:
            return empty

    # Normalise column names
    col_map = {}
    for target, canonical in _ENRICHMENT_RENAMES.items():
        found = _find_col(raw.columns, [target])
        if found:
            col_map[found] = canonical
    raw = raw.rename(columns=col_map)

    # Detect amount column
    amt_col = _find_col(raw.columns, ["base_amt", "amount", "amt", "base_amount"])

    # Build per-party aggregates by exploding src and dst
    records = []
    for role_col in [src_col, dst_col]:
        chunk = raw[[role_col]].copy()
        chunk = chunk.rename(columns={role_col: "party_id"})
        chunk["party_id"] = chunk["party_id"].astype(str)

        chunk["_amt"] = raw[amt_col].values if amt_col else 0.0
        chunk["_is_laun"] = (
            raw["is_laundering"].fillna(0).astype(int).values
            if "is_laundering" in raw.columns else 0
        )
        chunk["_laun_type"] = (
            raw["laundering_type"].fillna("").astype(str).values
            if "laundering_type" in raw.columns else ""
        )

        # Cross-border: sender_location != receiver_location
        if "sender_bank_location" in raw.columns and "receiver_bank_location" in raw.columns:
            s_loc = raw["sender_bank_location"].fillna("").astype(str).values
            r_loc = raw["receiver_bank_location"].fillna("").astype(str).values
            chunk["_cross_border"] = (s_loc != r_loc).astype(int)
            chunk["_jurisdictions"] = [
                f"{s}|{r}" for s, r in zip(s_loc, r_loc)
            ]
        else:
            chunk["_cross_border"] = 0
            chunk["_jurisdictions"] = ""

        # Cross-currency
        if "payment_currency" in raw.columns and "received_currency" in raw.columns:
            p_cur = raw["payment_currency"].fillna("").astype(str).values
            r_cur = raw["received_currency"].fillna("").astype(str).values
            chunk["_cross_currency"] = (p_cur != r_cur).astype(int)
            chunk["_currencies"] = [
                f"{p}|{r}" for p, r in zip(p_cur, r_cur)
            ]
        else:
            chunk["_cross_currency"] = 0
            chunk["_currencies"] = ""

        records.append(chunk)

    combined = pd.concat(records, ignore_index=True)

    # Group by party
    def _agg_party(grp):
        jurisdictions = set()
        for j in grp["_jurisdictions"]:
            if j:
                jurisdictions.update(j.split("|"))
        jurisdictions.discard("")

        currencies = set()
        for c in grp["_currencies"]:
            if c:
                currencies.update(c.split("|"))
        currencies.discard("")

        laun_types = set()
        for lt in grp["_laun_type"]:
            if lt and lt != "0" and lt.lower() != "nan":
                laun_types.add(lt)

        return pd.Series({
            "txn_count": len(grp),
            "total_amt": float(grp["_amt"].sum()),
            "laundering_txn_count": int(grp["_is_laun"].sum()),
            "laundering_types": ";".join(sorted(laun_types)) if laun_types else "",
            "cross_border_count": int(grp["_cross_border"].sum()),
            "cross_currency_count": int(grp["_cross_currency"].sum()),
            "unique_jurisdictions": len(jurisdictions),
            "unique_currencies": len(currencies),
        })

    enrichment = combined.groupby("party_id").apply(_agg_party).reset_index()
    logger.info(f"Enrichment aggregated for {len(enrichment):,} parties")
    return enrichment


def _join_with_edges(
    raw: pd.DataFrame, tran_col: str, data_dir: Path
) -> Tuple[pd.DataFrame, str | None, str | None]:
    """Join enrichment rows with edges_td.csv to get src/dst per transaction."""
    edges_path = data_dir / "edges_td.csv"
    if not edges_path.exists():
        logger.warning("edges_td.csv not found — cannot join enrichment by tran_id")
        return raw, None, None

    edges = pd.read_csv(edges_path)
    edges.columns = [c.strip() for c in edges.columns]

    e_src = _find_col(edges.columns, _SRC_CANDIDATES)
    e_dst = _find_col(edges.columns, _DST_CANDIDATES)
    e_tran = _find_col(edges.columns, _TRAN_ID_CANDIDATES)

    if e_src is None or e_dst is None:
        logger.warning(f"Cannot detect src/dst in edges_td.csv: {edges.columns.tolist()}")
        return raw, None, None

    join_key = e_tran if e_tran else None
    if join_key is None:
        # Use row-index alignment if edges and enrichment have same length
        if len(edges) == len(raw):
            raw[e_src] = edges[e_src].values
            raw[e_dst] = edges[e_dst].values
            return raw, e_src, e_dst
        logger.warning("No tran_id in edges and row counts differ — cannot join")
        return raw, None, None

    merged = raw.merge(edges[[join_key, e_src, e_dst]], left_on=tran_col, right_on=join_key, how="left")
    return merged, e_src, e_dst
