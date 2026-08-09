"""Extract retrosynthetic templates from USPTO reaction data using RDChiral.

Reads the normalized USPTO TSV produced by download_uspto.py:

    reaction_id <TAB> reactants.reagents>...>products

and produces an ASKCOS-compatible retro template JSON array (the format that
`deploy.sh seed-db -r <templates.json.gz>` imports into the `retro_templates`
MongoDB collection). Each template document carries the standard ASKCOS fields:

    {
      "index": 0,
      "smiles": "<forward reaction smiles>",
      "reaction_smarts": "<retro reaction SMARTS ...>>...>",
      "retro_rule": "<same retro reaction SMARTS>",
      "count": 12,                 // number of reactions that produced this template
      "selector_id": 0,
      "template_relevance_id": 0
    }

The treebuilder matches templates by the retro `reaction_smarts`, so that field
is the critical one. Identical extracted templates are aggregated under a
running count (frequency), which lets downstream steps rank/select templates.

Usage:
    python extract_templates.py --in uspto_reactions.tsv.gz \
        --out retro_templates.json.gz --min-count 2 --max-examples 200000

Large USPTO runs are memory-heavy; use --max-examples to cap the number of
reactions processed (e.g. 200k -> ~tens of minutes and a few tens of MB).
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import json
import logging
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from rdkit import Chem
from rdkit.Chem import AllChem
from rdchiral.template_extractor import extract_from_reaction

logger = logging.getLogger("extract_templates")

# Minimum number of conserved (mapped) product atoms required before we trust a
# mapping enough to attempt RDChiral extraction. Byproducts may be unmapped.
MIN_MAPPED_ATOMS = 3

try:  # CGRtools does robust atom-mapping for bond-forming reactions; optional.
    from CGRtools import from_rdkit_molecule as _cgr_from_rdkit
    from CGRtools import to_rdkit_molecule as _cgr_to_rdkit
    _HAS_CGRTOOLS = True
except Exception:  # pragma: no cover
    _HAS_CGRTOOLS = False


def split_reaction(rxn_smiles: str) -> tuple[str, str]:
    """Split a reaction SMILES into (reactants_side, products_side).

    Lowe's rxnsmiles uses 'reactants.reagents>>products'. We pass the whole
    left-of-`>>` group as reactants (including any reagents) and the right side
    as products. This is the standard simplification used by template pipelines;
    RDChiral only needs reactants and products.
    """
    reactants, sep, products = rxn_smiles.partition(">>")
    if not sep:
        return "", ""
    return reactants, products


def _atom_map_components(component_smiles_list: list[str]) -> list[Chem.Mol]:
    """Parse a list of SMILES into molecules, assigning a unique atom-map tag to
    every atom so that the combined reactant and product sets share a numbering
    scheme (required by RDChiral's template extraction)."""
    mols = []
    offset = 0
    for smi in component_smiles_list:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            return []  # signal failure
        mol = AllChem.RemoveHs(mol)
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + offset + 1)
        offset += mol.GetNumAtoms()
        mols.append(mol)
    return mols


def _assign_product_maps(reactant_mols, product_smiles: str) -> list[Chem.Mol] | None:
    """Atom-map each product to the combined reactant set via substructure match.

    Returns a list of product mols with atom-map numbers aligned to the reactant
    numbering, or None if a product cannot be mapped (reaction is not atom
    conserving in the strict sense RDChiral expects). This RDKit fallback only
    handles reactions where the product is a connected substructure of the
    combined reactants (e.g. simple rearrangements); CGRtools is preferred.
    """
    combined = reactant_mols[0]
    for _mol in reactant_mols[1:]:
        combined = Chem.CombineMols(combined, _mol)
    combined = Chem.Mol(combined)
    mapped_products = []
    for smi in product_smiles.split("."):
        pmol = Chem.MolFromSmiles(smi)
        if pmol is None:
            return None
        pmol = AllChem.RemoveHs(pmol)
        match = combined.GetSubstructMatch(pmol)
        if not match or len(match) != pmol.GetNumAtoms():
            return None
        for atom in pmol.GetAtoms():
            atom.SetAtomMapNum(match[atom.GetIdx()] + 1)
        mapped_products.append(pmol)
    return mapped_products


def _merge_products(mapped_products: list[Chem.Mol]) -> str | None:
    """Combine product mols into a single SMILES string (dot-separated)."""
    try:
        return ".".join(Chem.MolToSmiles(p) for p in mapped_products)
    except Exception:
        return None


def _cgr_molecule(smi: str):
    """Build a CGRtools molecule from a SMILES string, or None on failure."""
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    mol = AllChem.RemoveHs(mol)
    return _cgr_from_rdkit(mol)


def _cgr_normalize_ids(m):
    """Renumber a CGRtools molecule's atom ids to dense 1..N."""
    ids = [i for i, _ in m.atoms()]
    return m.remap({old: new + 1 for new, old in enumerate(sorted(ids))})


def _cgr_to_rdkit_safe(m):
    """Convert a CGRtools molecule to RDKit, or None on sanitization failure.

    Some USPTO reactions contain aromatic substructures that CGRtools cannot
    re-kekulize cleanly on the way back to RDKit (KekulizeException). These are
    pathological single reactions; we skip them rather than abort the whole run.
    """
    try:
        return _cgr_to_rdkit(m.copy())
    except Exception:
        return None


def _map_reaction_cgrtools(reactant_smiles: list[str], product_smiles: list[str]):
    """Atom-map a reaction with CGRtools.

    Each reactant fragment is a (usually connected) subgraph of a product, so we
    map each reactant onto each product with ``get_mapping`` and merge the
    results greedily, keeping the assignment that conserves the most atoms. This
    handles bond-forming reactions that RDKit substructure matching cannot
    (disconnected reactants -> connected product).

    Returns (reactants_str, products_str) with a single consistent atom-map
    numbering, or None if the reaction cannot be mapped.
    """
    r_raw = [_cgr_molecule(s) for s in reactant_smiles]
    p_raw = [_cgr_molecule(s) for s in product_smiles]
    if any(m is None for m in r_raw + p_raw):
        return None
    r_mols = [_cgr_normalize_ids(m) for m in r_raw]
    p_mols = [_cgr_normalize_ids(m) for m in p_raw]

    r_global = {}
    gid = 1
    for fi, m in enumerate(r_mols):
        for local, _ in m.atoms():
            r_global[(fi, local)] = gid
            gid += 1
    p_global = {}
    gid = 1
    for pj, m in enumerate(p_mols):
        for local, _ in m.atoms():
            p_global[(pj, local)] = gid
            gid += 1

    # Candidate mappings: (conserved_atoms, [(product_global, reactant_global), ...])
    # get_mcs_mapping returns the *maximal common substructure* (partial) mapping,
    # which is what we need: byproducts such as water do not need to be mapped —
    # RDChiral only needs the reaction-center atoms to be consistent.
    candidates = []
    for fi, rm in enumerate(r_mols):
        for pj, pm in enumerate(p_mols):
            try:
                mappings = list(rm.get_mcs_mapping(pm))
            except Exception:
                continue
            for mdict in mappings:
                pairs = [
                    (p_global[(pj, pl)], r_global[(fi, rl)])
                    for rl, pl in mdict.items()
                    if (fi, rl) in r_global
                ]
                candidates.append((len(pairs), pairs))
    candidates.sort(key=lambda x: -x[0])

    prod_to_reactant: dict[int, int] = {}
    for _, pairs in candidates:
        for pl, rg in pairs:
            prod_to_reactant.setdefault(pl, rg)

    # Residual element-based pass: for each unmapped product atom, pair it with
    # an unused reactant atom of the same element. This completes the mapping for
    # byproducts / leaving groups (e.g. the water-O that leaves an alcohol/acid),
    # which CGRtools' MCS does not return for single atoms. RDChiral needs a
    # consistent per-atom correspondence to validate the extracted template.
    used_r = {rg for rg in prod_to_reactant.values()}
    by_element: dict[str, list[int]] = {}
    for fi, m in enumerate(r_mols):
        for local, atom in m.atoms():
            rg = r_global[(fi, local)]
            if rg not in used_r:
                by_element.setdefault(str(atom), []).append(rg)
    for pj, pm in enumerate(p_mols):
        for local, atom in pm.atoms():
            gpl = p_global[(pj, local)]
            if gpl in prod_to_reactant:
                continue
            pool = by_element.get(str(atom))
            if pool:
                prod_to_reactant[gpl] = pool.pop()

    # Require a non-trivial conserved core so RDChiral has a reaction center to
    # extract. RDChiral remains the final quality gate for correctness.
    if len(prod_to_reactant) < MIN_MAPPED_ATOMS:
        return None

    # Rebuild reactants and products with atom-map numbers = their global id.
    # Each reactant atom keeps its cross-reaction global id; each product atom
    # gets the global id of the reactant atom it maps to, so conserved atoms
    # share a map number (required by RDChiral).
    mapped_reactants = []
    for fi, m in enumerate(r_mols):
        pm = _cgr_to_rdkit_safe(m)
        if pm is None:
            return None
        src = {local: rg for (f, local), rg in r_global.items() if f == fi}
        for atom in pm.GetAtoms():
            atom.SetAtomMapNum(src[atom.GetIdx() + 1])
        mapped_reactants.append(pm)
    reactants_str = ".".join(Chem.MolToSmiles(m) for m in mapped_reactants)

    mapped_products = []
    for pj, pm in enumerate(p_mols):
        pm = _cgr_to_rdkit_safe(pm)
        if pm is None:
            return None
        for atom in pm.GetAtoms():
            global_id = p_global[(pj, atom.GetIdx() + 1)]
            rg = prod_to_reactant.get(global_id)
            if rg is not None:  # leave byproducts (e.g. water) unmapped
                atom.SetAtomMapNum(rg)
        mapped_products.append(pm)
    products_str = ".".join(Chem.MolToSmiles(m) for m in mapped_products)
    return reactants_str, products_str


def _map_reaction_rdkit(reactant_smiles: list[str], product_smiles: str):
    """RDKit-only fallback mapper (connected-product case)."""
    reactant_mols = _atom_map_components(reactant_smiles)
    if not reactant_mols:
        return None
    mapped_products = _assign_product_maps(reactant_mols, product_smiles)
    if mapped_products is None:
        return None
    products_str = _merge_products(mapped_products)
    if not products_str:
        return None
    reactants_str = ".".join(Chem.MolToSmiles(m) for m in reactant_mols)
    return reactants_str, products_str


def _map_reaction(reactant_smiles: list[str], product_smiles: str):
    """Atom-map a reaction, preferring CGRtools and falling back to RDKit."""
    if _HAS_CGRTOOLS:
        mapped = _map_reaction_cgrtools(reactant_smiles, product_smiles.split("."))
        if mapped is not None:
            return mapped
    return _map_reaction_rdkit(reactant_smiles, product_smiles)


def reaction_to_template(rxn_id: str, rxn_smiles: str, forward_smiles: str) -> dict | None:
    """Run RDChiral extraction for one reaction. Returns ASKCOS template or None.

    The normalized USPTO data already carries complete atom mapping (e.g.
    [Br:1]); re-running CGRtools/RDKit mapping on every reaction is both slow
    (complex molecules can take seconds) and lowers the yield. We therefore hand
    RDChiral the existing maps directly and only fall back to re-mapping when
    the reaction carries no usable mapping.
    """
    reactants, products = split_reaction(rxn_smiles)
    if not reactants or not products:
        return None

    # Prefer the atom maps already present in the data. If neither side has an
    # atom map, fall back to re-mapping so un-mapped input still works.
    if ":" in reactants and ":" in products:
        reactants_str, products_str = reactants, products
    else:
        try:
            pair = _map_reaction(reactants.split("."), products)
        except Exception as exc:
            logger.debug("Mapping error for %s: %s", rxn_id, exc)
            return None
        if pair is None:
            return None
        reactants_str, products_str = pair

    try:
        # RDChiral logs validation failures unconditionally to stdout. On a
        # full-Corpus run (1.8M reactions) this floods the terminal and slows
        # extraction, so we silence it; only the final count is reported.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = extract_from_reaction({
                "_id": rxn_id,
                "reactants": reactants_str,
                "products": products_str,
            })
    except Exception as exc:  # RDChiral can raise on pathological inputs
        logger.debug("RDChiral error for %s: %s", rxn_id, exc)
        return None
    if not result or "reaction_smarts" not in result:
        return None
    retro_smarts = result["reaction_smarts"]
    if not retro_smarts or ">>" not in retro_smarts:
        return None
    return {
        "smiles": forward_smiles,
        "reaction_smarts": retro_smarts,
        "retro_rule": retro_smarts,
        "reaction_id": rxn_id,
    }


def iter_reactions(path: str):
    """Yield (rxn_id, rxn_smiles, forward_smiles) from the normalized TSV."""
    open_fn = gzip.open if path.endswith(".gz") else open
    with open_fn(path, "rt", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            rxn_id, rxn_smiles = parts[0], parts[1]
            if ">>" not in rxn_smiles:
                continue
            # Canonical forward smiles for the 'smiles' field (best-effort).
            forward_smiles = rxn_smiles
            try:
                forward_smiles = Chem.MolToSmiles(Chem.MolFromSmiles(rxn_smiles))
            except Exception:
                pass
            yield rxn_id, rxn_smiles, forward_smiles


def _worker(item):
    """ProcessPoolExecutor worker: extract one reaction's template (or None)."""
    rxn_id, rxn_smiles, forward_smiles = item
    try:
        return reaction_to_template(rxn_id, rxn_smiles, forward_smiles)
    except Exception as exc:  # never let one reaction kill a worker
        logger.debug("Worker error for %s: %s", rxn_id, exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", default="uspto_reactions.tsv.gz")
    parser.add_argument("--out", default="retro_templates.json.gz")
    parser.add_argument("--min-count", type=int, default=2,
                        help="drop templates occurring fewer than this many times")
    parser.add_argument("--max-examples", type=int, default=200_000,
                        help="cap on number of reactions to process")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of parallel processes (0 = all cores)")
    parser.add_argument("--task-timeout", type=float, default=60,
                        help="per-reaction hard timeout in seconds (parallel mode)")
    parser.add_argument("--no-cgrtools", action="store_true",
                        help="force the RDKit-only atom-mapping path (skip CGRtools)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.no_cgrtools:
        logger.info("Forcing RDKit-only mapper (--no-cgrtools)")
        global _HAS_CGRTOOLS
        _HAS_CGRTOOLS = False

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    by_smarts: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    processed = 0
    skipped = 0

    def accumulate(tpl):
        nonlocal skipped
        if tpl is None:
            skipped += 1
            return
        key = tpl["reaction_smarts"]
        counts[key] += 1
        by_smarts.setdefault(key, tpl)

    n_workers = args.workers
    if n_workers == 0:
        n_workers = os.cpu_count() or 1

    if n_workers > 1:
        # 用 as_completed 维持固定窗口的在途任务：主循环持续提交，任意一个
        # future 完成就立刻收割并补新任务，保证 worker 始终满载。避免之前
        # popleft().result() 顺序等待最老 future 时，遇到慢任务阻塞导致其他
        # worker 空闲（并行度只有满配的 1/4）。
        from collections import deque
        import concurrent.futures
        logger.info("Extracting with %d worker processes", n_workers)
        window = max(n_workers * 4, 64)
        task_timeout = getattr(args, "task_timeout", 60)

        pending: deque = deque()
        it = iter_reactions(args.inp)

        def _next_result(f):
            """Wait up to task_timeout for a future and return its result or None."""
            nonlocal skipped
            try:
                return f.result(timeout=task_timeout)
            except concurrent.futures.TimeoutError:
                logger.warning("Task timed out after %ss; skipping", task_timeout)
                skipped += 1
                return None
            except Exception:
                skipped += 1
                return None

        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            # 预填满窗口
            for trail in it:
                if processed >= args.max_examples:
                    break
                pending.append(ex.submit(_worker, trail))
                if len(pending) >= window:
                    break
            while pending:
                done, _ = concurrent.futures.wait(
                    pending, timeout=task_timeout,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                if not done:
                    # 窗口内所有任务都超时：逐个收割（每个再等 task_timeout）
                    for f in list(pending):
                        tpl = _next_result(f)
                        processed += 1
                        accumulate(tpl)
                        pending.remove(f)
                        if processed % 5_000 == 0:
                            logger.info("processed=%d kept=%d skipped=%d",
                                        processed, len(by_smarts), skipped)
                    continue
                for f in done:
                    tpl = _next_result(f)
                    processed += 1
                    accumulate(tpl)
                    pending.remove(f)
                    if processed % 5_000 == 0:
                        logger.info("processed=%d kept=%d skipped=%d",
                                    processed, len(by_smarts), skipped)
                # 补足窗口：持续消费迭代器，直到窗口填满或达到 max_examples
                while len(pending) < window and processed + len(pending) < args.max_examples:
                    try:
                        trail = next(it)
                    except StopIteration:
                        break
                    pending.append(ex.submit(_worker, trail))
            # 收尾：`with` 块的 shutdown(wait=True) 会永久等一个卡死在 RDChiral
            # C 层、不响应结束信号的 worker，导致进程挂死。因此显式终止所有
            # worker 子进程，而不是等待优雅关闭。
            ex.shutdown(wait=False, cancel_futures=True)
            import multiprocessing as _mp
            for p in _mp.active_children():
                if p.is_alive():
                    p.terminate()
            for p in _mp.active_children():
                p.join(timeout=5)
    else:
        for rxn_id, rxn_smiles, forward_smiles in iter_reactions(args.inp):
            if processed >= args.max_examples:
                break
            processed += 1
            tpl = reaction_to_template(rxn_id, rxn_smiles, forward_smiles)
            accumulate(tpl)
            if processed % 20_000 == 0:
                logger.info("processed=%d kept=%d skipped=%d",
                            processed, len(by_smarts), skipped)

    logger.info("Done: processed=%d unique_templates=%d skipped=%d",
                processed, len(by_smarts), skipped)

    # Assemble final documents with ASKCOS schema and running frequency.
    docs: list[dict] = []
    for idx, (smarts, tpl) in enumerate(by_smarts.items()):
        count = counts[smarts]
        if count < args.min_count:
            continue
        docs.append({
            "index": idx,
            "smiles": tpl["smiles"],
            "reaction_smarts": smarts,
            "retro_rule": smarts,
            "count": count,
            "selector_id": 0,
            "template_relevance_id": 0,
        })

    logger.info("Writing %d templates (>= count %d) -> %s",
                len(docs), args.min_count, args.out)
    open_fn = gzip.open if args.out.endswith(".gz") else open
    with open_fn(args.out, "wt", encoding="utf-8") as fh:
        json.dump(docs, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main())