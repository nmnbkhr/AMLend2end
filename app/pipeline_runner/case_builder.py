"""
Case Construction & Typology Detection (Phase B)

Converts tiered risk queues into investigation-ready AML cases.
Each case is a k-hop ego subgraph around high-risk seed entities,
with rule-based typology tags.

Inputs:
    queues/risk_queue.parquet
    queues/operating_point.json  (optional)
    data/edges_td.csv
    data/node_td.csv
    data/alert_nodes_td.csv

Outputs:
    cases/case_index.parquet
    cases/case_summary.json
    cases/case_<case_id>.json
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

import pandas as pd

logger = logging.getLogger(__name__)

# Typology thresholds
FAN_RATIO_THRESHOLD = 3.0       # out/in (or in/out) ratio for fan detection
HUB_DOMINANCE_THRESHOLD = 5.0   # max_degree / avg_degree
CYCLE_MAX_LENGTH = 3
OVERLAP_MERGE_THRESHOLD = 0.30   # 30% node overlap to merge cases

# Default seed selection
DEFAULT_SEED_TIERS = ["T1", "T2"]
DEFAULT_MAX_PERCENTILE = 2.0


# ── Graph helpers ──


def _load_edges(edges_path: Path) -> pd.DataFrame:
    """Load edges and normalise column names to src/dst."""
    df = pd.read_csv(edges_path)
    df.columns = [c.strip().lower() for c in df.columns]

    col_map = {}
    for src_name, dst_name in [("source", "target"), ("src", "dst"), ("from", "to")]:
        if src_name in df.columns and dst_name in df.columns:
            col_map = {src_name: "src", dst_name: "dst"}
            break

    if col_map:
        df = df.rename(columns=col_map)

    if "src" not in df.columns or "dst" not in df.columns:
        raise ValueError(f"Cannot detect src/dst columns. Found: {df.columns.tolist()}")

    df["src"] = df["src"].astype(str)
    df["dst"] = df["dst"].astype(str)
    return df


def _build_adjacency(edges_df: pd.DataFrame) -> Dict[str, Set[str]]:
    """Build undirected adjacency dict from edge dataframe (vectorized)."""
    adj: Dict[str, Set[str]] = defaultdict(set)
    srcs = edges_df["src"].values
    dsts = edges_df["dst"].values
    for i in range(len(srcs)):
        adj[srcs[i]].add(dsts[i])
        adj[dsts[i]].add(srcs[i])
    return dict(adj)


def _build_directed(edges_df: pd.DataFrame) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build directed out-adj and in-adj dicts (vectorized)."""
    out_adj: Dict[str, Set[str]] = defaultdict(set)
    in_adj: Dict[str, Set[str]] = defaultdict(set)
    srcs = edges_df["src"].values
    dsts = edges_df["dst"].values
    for i in range(len(srcs)):
        out_adj[srcs[i]].add(dsts[i])
        in_adj[dsts[i]].add(srcs[i])
    return dict(out_adj), dict(in_adj)


class _UnionFind:
    """Disjoint-set / Union-Find for fast case merging."""

    def __init__(self):
        self.parent: Dict[int, int] = {}
        self.rank: Dict[int, int] = {}

    def find(self, x: int) -> int:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _k_hop_neighbors(seed: str, adj: Dict[str, Set[str]], k: int) -> Set[str]:
    """Return all nodes within k hops of seed (including seed)."""
    visited: Set[str] = {seed}
    frontier: Set[str] = {seed}
    for _ in range(k):
        next_frontier: Set[str] = set()
        for node in frontier:
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def _subgraph_edges(nodes: Set[str], edges_df: pd.DataFrame) -> pd.DataFrame:
    """Return edges where both endpoints are in the node set."""
    mask = edges_df["src"].isin(nodes) & edges_df["dst"].isin(nodes)
    return edges_df[mask].copy()


# ── Typology detection ──


def _detect_typologies(
    nodes: Set[str],
    sub_edges: pd.DataFrame,
    sar_ids: Set[str],
) -> List[str]:
    """Detect rule-based AML typologies for a case subgraph."""
    typologies = []

    if sub_edges.empty:
        if nodes & sar_ids:
            typologies.append("SAR_PROXIMITY")
        return typologies

    # Directed degrees within subgraph (vectorized)
    out_deg: Dict[str, int] = defaultdict(int)
    in_deg: Dict[str, int] = defaultdict(int)
    srcs = sub_edges["src"].values
    dsts = sub_edges["dst"].values
    for i in range(len(srcs)):
        out_deg[srcs[i]] += 1
        in_deg[dsts[i]] += 1

    # FAN_OUT: any node with out >> in
    for n in nodes:
        od = out_deg.get(n, 0)
        ind = in_deg.get(n, 0)
        if od >= 3 and (ind == 0 or od / max(ind, 1) >= FAN_RATIO_THRESHOLD):
            typologies.append("FAN_OUT")
            break

    # FAN_IN: any node with in >> out
    for n in nodes:
        ind = in_deg.get(n, 0)
        od = out_deg.get(n, 0)
        if ind >= 3 and (od == 0 or ind / max(od, 1) >= FAN_RATIO_THRESHOLD):
            typologies.append("FAN_IN")
            break

    # CIRCULAR_FLOW: detect cycles of length <= CYCLE_MAX_LENGTH
    adj_out: Dict[str, Set[str]] = defaultdict(set)
    for i in range(len(srcs)):
        adj_out[srcs[i]].add(dsts[i])

    found_cycle = False
    for start in nodes:
        if found_cycle:
            break
        # BFS/DFS for short cycles
        stack = [(start, [start])]
        while stack and not found_cycle:
            current, path = stack.pop()
            for neighbor in adj_out.get(current, set()):
                if neighbor == start and len(path) >= 2:
                    found_cycle = True
                    break
                if neighbor not in path and len(path) < CYCLE_MAX_LENGTH:
                    stack.append((neighbor, path + [neighbor]))

    if found_cycle:
        typologies.append("CIRCULAR_FLOW")

    # HUB_DOMINANCE: max degree / avg degree
    total_deg = {n: out_deg.get(n, 0) + in_deg.get(n, 0) for n in nodes}
    if total_deg:
        max_d = max(total_deg.values())
        avg_d = sum(total_deg.values()) / len(total_deg)
        if avg_d > 0 and max_d / avg_d >= HUB_DOMINANCE_THRESHOLD:
            typologies.append("HUB_DOMINANCE")

    # SAR_PROXIMITY: SAR-labelled entity in subgraph
    if nodes & sar_ids:
        typologies.append("SAR_PROXIMITY")

    return sorted(set(typologies))


# ── Main builder ──


def build_cases(
    run_dir: Path,
    hop_k: int = 2,
) -> Dict[str, Any]:
    """
    Build investigation cases from the risk queue.

    Args:
        run_dir: Root artifact directory for the run.
        hop_k: Number of hops for ego-graph expansion.

    Returns:
        Summary dict (also persisted as case_summary.json).
    """
    data_dir = run_dir / "data"
    queues_dir = run_dir / "queues"
    cases_dir = run_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load risk queue ──
    queue_parquet = queues_dir / "risk_queue.parquet"
    queue_csv = queues_dir / "risk_queue.csv"

    if queue_parquet.exists():
        queue_df = pd.read_parquet(queue_parquet)
    elif queue_csv.exists():
        queue_df = pd.read_csv(queue_csv)
    else:
        raise FileNotFoundError("risk_queue.parquet/csv not found — run Phase A first")

    logger.info(f"Loaded risk queue: {len(queue_df):,} entities")

    # ── 2. Determine seed selection from operating point ──
    op_path = queues_dir / "operating_point.json"
    if op_path.exists():
        try:
            with open(op_path) as f:
                op = json.load(f)
            payload = op.get("payload", {})
            seed_tiers = payload.get("tiers", DEFAULT_SEED_TIERS)
            max_pct = payload.get("top_percent", DEFAULT_MAX_PERCENTILE)
            logger.info(f"Using operating point: tiers={seed_tiers}, top_percent={max_pct}")
        except Exception as e:
            logger.warning(f"Failed to read operating_point.json: {e}")
            seed_tiers = DEFAULT_SEED_TIERS
            max_pct = DEFAULT_MAX_PERCENTILE
    else:
        seed_tiers = DEFAULT_SEED_TIERS
        max_pct = DEFAULT_MAX_PERCENTILE
        logger.info(f"No operating point — using defaults: tiers={seed_tiers}, top_percent={max_pct}")

    # Select seeds: percentile filter first, then tier filter
    seeds_df = queue_df[queue_df["percentile"] <= max_pct].copy()
    seeds_df = seeds_df[seeds_df["tier"].isin(seed_tiers)]
    seed_ids = set(seeds_df["entity_id"].astype(str))
    logger.info(f"Selected {len(seed_ids):,} seed entities")

    if not seed_ids:
        summary = {
            "total_cases": 0,
            "seed_count": 0,
            "typology_counts": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hop_k": hop_k,
            "seed_tiers": seed_tiers,
            "max_percentile": max_pct,
        }
        (cases_dir / "case_summary.json").write_text(json.dumps(summary, indent=2))
        # Empty case index
        pd.DataFrame(columns=[
            "case_id", "tier", "risk_score", "entity_count", "edge_count",
            "sar_count", "typologies", "seed_entities",
        ]).to_parquet(cases_dir / "case_index.parquet", index=False)
        return summary

    # ── 3. Load edges and build adjacency ──
    edges_path = data_dir / "edges_td.csv"
    if edges_path.exists():
        edges_df = _load_edges(edges_path)
        adj = _build_adjacency(edges_df)
        logger.info(f"Loaded {len(edges_df):,} edges, {len(adj):,} nodes in adjacency")
    else:
        edges_df = pd.DataFrame(columns=["src", "dst"])
        adj = {}
        logger.warning("No edges_td.csv — cases will be single-node")

    # SAR ids for typology detection
    sar_ids = set(queue_df[queue_df["is_sar"] == 1]["entity_id"].astype(str))

    # Queue lookup for metadata (vectorized — avoid iterrows on 855K rows)
    queue_df["entity_id"] = queue_df["entity_id"].astype(str)
    queue_lookup = queue_df.set_index("entity_id").to_dict("index")

    # ── 4. Build ego graphs per seed ──
    raw_cases: List[Dict[str, Any]] = []
    for seed_id in seed_ids:
        nodes = _k_hop_neighbors(seed_id, adj, hop_k)
        raw_cases.append({
            "seeds": {seed_id},
            "nodes": nodes,
        })

    logger.info(f"Built {len(raw_cases)} ego graphs, starting merge...")

    # ── 5. Merge overlapping cases (Union-Find based) ──
    # Build node→case_index mapping for overlap detection
    node_to_cases: Dict[str, List[int]] = defaultdict(list)
    for i, rc in enumerate(raw_cases):
        for n in rc["nodes"]:
            node_to_cases[n].append(i)

    uf = _UnionFind()
    for case_indices in node_to_cases.values():
        if len(case_indices) > 1:
            # These cases share a node — check overlap and merge
            first = case_indices[0]
            for other in case_indices[1:]:
                ri, rj = uf.find(first), uf.find(other)
                if ri != rj:
                    uf.union(ri, rj)

    # Group cases by root
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(raw_cases)):
        groups[uf.find(i)].append(i)

    merged_cases: List[Dict[str, Any]] = []
    for members in groups.values():
        combined_seeds: Set[str] = set()
        combined_nodes: Set[str] = set()
        for idx in members:
            combined_seeds |= raw_cases[idx]["seeds"]
            combined_nodes |= raw_cases[idx]["nodes"]
        merged_cases.append({"seeds": combined_seeds, "nodes": combined_nodes})

    raw_cases = merged_cases
    logger.info(f"Merged into {len(raw_cases)} cases from {len(seed_ids)} seeds")

    # ── 6. Build final case objects ──
    case_records = []
    for raw in raw_cases:
        case_id = str(uuid4())
        nodes = raw["nodes"]
        seeds = raw["seeds"]
        sub_edges = _subgraph_edges(nodes, edges_df)

        # Tier = max tier among seeds (T1 > T2 > T3 > T4)
        tier_priority = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}
        best_tier = "T4"
        max_risk_score = 0.0
        all_reasons: Set[str] = set()

        for s in seeds:
            info = queue_lookup.get(s, {})
            s_tier = info.get("tier", "T4")
            if tier_priority.get(s_tier, 3) < tier_priority.get(best_tier, 3):
                best_tier = s_tier
            s_score = info.get("risk_score", 0.0)
            if s_score > max_risk_score:
                max_risk_score = s_score
            reasons_str = info.get("reasons", "")
            if reasons_str:
                for r in reasons_str.split(";"):
                    r = r.strip()
                    if r:
                        all_reasons.add(r)

        # Case stats
        sar_in_case = len(nodes & sar_ids)
        degrees = []
        for n in nodes:
            degrees.append(len(adj.get(n, set())))

        # Typology detection
        typologies = _detect_typologies(nodes, sub_edges, sar_ids)

        # Build entity list with metadata
        entities = []
        for n in sorted(nodes):
            info = queue_lookup.get(n, {})
            entities.append({
                "entity_id": n,
                "entity_type": str(info.get("entity_type", "unknown")),
                "is_sar": int(info.get("is_sar", 0)),
                "is_seed": n in seeds,
                "risk_score": float(info.get("risk_score", 0.0)),
                "tier": info.get("tier", "T4"),
                "degree": int(info.get("degree", 0)),
            })

        # Build edge list (vectorized)
        edge_list = []
        if not sub_edges.empty:
            edge_records = sub_edges.to_dict("records")
            for rec in edge_records:
                edge_entry = {"src": rec["src"], "dst": rec["dst"]}
                if "base_amt" in rec and pd.notna(rec["base_amt"]):
                    edge_entry["amount"] = float(rec["base_amt"])
                if "tx_type" in rec and pd.notna(rec["tx_type"]):
                    edge_entry["tx_type"] = str(rec["tx_type"])
                edge_list.append(edge_entry)

        case_obj = {
            "case_id": case_id,
            "tier": best_tier,
            "risk_score": round(max_risk_score, 6),
            "typologies": typologies,
            "reasons": sorted(all_reasons),
            "seed_entities": sorted(seeds),
            "entity_count": len(nodes),
            "edge_count": len(sub_edges),
            "sar_count": sar_in_case,
            "degree_summary": {
                "min": min(degrees) if degrees else 0,
                "max": max(degrees) if degrees else 0,
                "mean": round(sum(degrees) / len(degrees), 2) if degrees else 0,
            },
            "entities": entities,
            "edges": edge_list,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save individual case file
        case_path = cases_dir / f"case_{case_id}.json"
        with open(case_path, "w") as f:
            json.dump(case_obj, f, indent=2)

        # Index record (no entities/edges for the index)
        case_records.append({
            "case_id": case_id,
            "tier": best_tier,
            "risk_score": round(max_risk_score, 6),
            "entity_count": len(nodes),
            "edge_count": len(sub_edges),
            "sar_count": sar_in_case,
            "typologies": ";".join(typologies),
            "seed_entities": ";".join(sorted(seeds)),
            "seed_count": len(seeds),
        })

    # ── 7. Save case index ──
    index_df = pd.DataFrame(case_records)
    index_df = index_df.sort_values("risk_score", ascending=False).reset_index(drop=True)
    index_df.to_parquet(cases_dir / "case_index.parquet", index=False)
    logger.info(f"Saved case index: {len(index_df)} cases")

    # ── 8. Build summary ──
    typology_counts: Dict[str, int] = defaultdict(int)
    for rec in case_records:
        for t in rec["typologies"].split(";"):
            t = t.strip()
            if t:
                typology_counts[t] += 1

    summary = {
        "total_cases": len(case_records),
        "seed_count": len(seed_ids),
        "hop_k": hop_k,
        "seed_tiers": seed_tiers,
        "max_percentile": max_pct,
        "typology_counts": dict(typology_counts),
        "tier_counts": index_df["tier"].value_counts().to_dict() if not index_df.empty else {},
        "total_entities_in_cases": int(index_df["entity_count"].sum()) if not index_df.empty else 0,
        "total_edges_in_cases": int(index_df["edge_count"].sum()) if not index_df.empty else 0,
        "total_sar_in_cases": int(index_df["sar_count"].sum()) if not index_df.empty else 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = cases_dir / "case_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Saved case summary: {summary['total_cases']} cases")

    return summary
