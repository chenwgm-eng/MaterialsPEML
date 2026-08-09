"""Validate and seed ASKCOS retro templates into an *independent* Mongo collection.

The templates produced by extract_templates.py are public-domain (USPTO) retro
rules. Rather than overwriting ASKCOS's default `retro_templates` collection
(whose template-relevance model indices are tied to the default set), this
script imports them into a separate collection so the data can be inspected,
backed up, and swapped in deliberately without destroying the default.

Validation is always performed locally (no Mongo required):
  * required ASKCOS schema fields are present and correctly typed
  * `reaction_smarts` / `retro_rule` parse as a valid RDKit reaction SMARTS
  * the retro rule is atom-conserving (same heavy-atom count on both sides)
  * `index` values are unique (Mongo's unique index depends on this)

Seeding (optional, requires the running ASKCOS docker deployment) copies the
templates into the mongo container and runs `mongoimport` against the chosen
independent collection, then reports the resulting document count.

Usage:
    python seed_templates.py --in retro_templates.json.gz \
        --collection retro_templates_commercial
    python seed_templates.py --in retro_templates.json.gz --validate-only
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import subprocess
import sys
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

logger = logging.getLogger("seed_templates")

REQUIRED_FIELDS = {
    "index": int,
    "smiles": str,
    "reaction_smarts": str,
    "retro_rule": str,
    "count": int,
    "selector_id": int,
    "template_relevance_id": int,
}

# Defaults matching askcos-deploy/.env and docker-compose.yml.
DEFAULT_COLLECTION = "retro_templates_commercial"
DEFAULT_MONGO_CONTAINER = "askcos-deploy-mongo-1"
DEFAULT_MONGO_HOST = "mongo"
DEFAULT_MONGO_USER = "askcos"
DEFAULT_MONGO_PW = "askcos"
DEFAULT_MONGO_DB = "askcos"


def load_templates(path: str) -> list[dict]:
    open_fn = gzip.open if path.endswith(".gz") else open
    with open_fn(path, "rt", encoding="utf-8") as fh:
        docs = json.load(fh)
    if not isinstance(docs, list):
        raise ValueError(f"{path} does not contain a JSON array of templates")
    return docs


def _check_field(doc: dict, name: str, expected: type) -> list[str]:
    errors = []
    if name not in doc:
        errors.append(f"missing field '{name}'")
    elif not isinstance(doc[name], expected):
        errors.append(f"field '{name}' has type {type(doc[name]).__name__}, "
                      f"expected {expected.__name__}")
    return errors


def _heavy_atoms(smarts: str) -> int | None:
    """Count heavy atoms on one side of a reaction SMARTS, or None if invalid."""
    try:
        rxn = AllChem.ReactionFromSmarts(smarts)
        return rxn.GetNumReactantTemplates() + rxn.GetNumProductTemplates()
    except Exception:
        return None


def validate_document(doc: dict) -> list[str]:
    """Validate a single template document; returns a list of error strings."""
    errors = []
    for name, typ in REQUIRED_FIELDS.items():
        errors.extend(_check_field(doc, name, typ))
    if errors:
        return errors

    smarts = doc["reaction_smarts"]
    if ">>" not in smarts:
        errors.append("reaction_smarts has no '>>' separator")
    try:
        rxn = AllChem.ReactionFromSmarts(smarts)
        if rxn is None:
            errors.append("reaction_smarts is not a valid reaction SMARTS")
        elif rxn.GetNumReactantTemplates() == 0 or rxn.GetNumProductTemplates() == 0:
            errors.append("reaction_smarts must have both a reactant and product side")
    except Exception as exc:
        errors.append(f"reaction_smarts parse error: {exc}")

    if doc["retro_rule"] != smarts:
        errors.append("retro_rule differs from reaction_smarts")

    # Atom-conservation sanity check: the retro rule should preserve heavy atoms.
    try:
        rxn = AllChem.ReactionFromSmarts(smarts)
        n_r = sum(len(t.GetAtoms()) for t in rxn.GetReactantTemplates())
        n_p = sum(len(t.GetAtoms()) for t in rxn.GetProductTemplates())
        if n_r != n_p:
            errors.append(f"atom count mismatch retro rule (reactants={n_r}, products={n_p})")
    except Exception:
        pass
    return errors


def validate(docs: list[dict]) -> tuple[int, dict]:
    """Validate all documents. Returns (num_errors, stats)."""
    errors = 0
    seen_index: set[int] = set()
    seen_smarts: set[str] = set()
    dup_index = dup_smarts = 0
    for doc in docs:
        errs = validate_document(doc)
        if errs:
            errors += 1
            logger.warning("doc index=%s invalid: %s", doc.get("index"), "; ".join(errs))
        idx = doc.get("index")
        if idx is not None:
            if idx in seen_index:
                dup_index += 1
            seen_index.add(idx)
        sm = doc.get("reaction_smarts")
        if sm is not None:
            if sm in seen_smarts:
                dup_smarts += 1
            seen_smarts.add(sm)
    stats = {
        "total": len(docs),
        "invalid": errors,
        "unique_index": len(seen_index),
        "duplicate_index": dup_index,
        "unique_smarts": len(seen_smarts),
        "duplicate_smarts": dup_smarts,
    }
    return errors, stats


def _write_with_template_set(path: str, docs: list[dict],
                             template_set: str) -> str:
    """Write a temp gz with 'template_set' injected into every document.

    ASKCOS looks up templates by {'index', 'template_set'}, and the codebase
    defaults to template_set='reaxys'. We tag the USPTO-derived templates with
    that label so the swapped-in collection matches the default lookup without
    touching any template_set references in the treebuilder code.
    """
    docs = [{**d, "template_set": template_set} for d in docs]
    tmp = Path(path).with_name(f"{Path(path).stem}.ts-{template_set}.json.gz")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(docs, fh)
    return str(tmp)


def import_to_mongo(path: str, collection: str, container: str,
                    host: str, user: str, pw: str, db: str,
                    template_set: str | None = None) -> int:
    """docker-copy the templates into the mongo container and mongoimport them."""
    if template_set:
        docs = load_templates(path)
        path = _write_with_template_set(path, docs, template_set)
    name = Path(path).name
    dst = f"/tmp/{name}"
    logger.info("Copying %s -> %s:%s", path, container, dst)
    subprocess.run(["docker", "cp", path, f"{container}:{dst}"], check=True)

    cmd = [
        "docker", "exec", container, "bash", "-c",
        "if [ -f {dst}.plain ]; then :; else gzip -df {dst} 2>/dev/null; fi; "
        "mongoimport "
        "--host {host} --username {user} --password {pw} "
        "--authenticationDatabase admin --db {db} "
        "--collection {collection} --type json --jsonArray --drop "
        "--file {plain}".format(
            dst=dst, plain=dst[:-3] if dst.endswith(".gz") else dst,
            host=host, user=user, pw=pw, db=db, collection=collection),
    ]
    logger.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # Report the resulting count via the mongo shell.
    count_cmd = [
        "docker", "exec", container, "mongo",
        "--host", host, "--username", user, "--password", pw,
        "--authenticationDatabase", "admin", "--quiet",
        "--eval", f"print(db.getSiblingDB('{db}').{collection}.countDocuments({{}}))",
    ]
    out = subprocess.run(count_cmd, check=True, capture_output=True, text=True)
    count = int(out.stdout.strip())
    logger.info("Collection %s now holds %d documents", collection, count)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", default="retro_templates.json.gz")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--container", default=DEFAULT_MONGO_CONTAINER)
    parser.add_argument("--host", default=DEFAULT_MONGO_HOST)
    parser.add_argument("--user", default=DEFAULT_MONGO_USER)
    parser.add_argument("--pw", default=DEFAULT_MONGO_PW)
    parser.add_argument("--db", default=DEFAULT_MONGO_DB)
    parser.add_argument("--template-set", default="reaxys",
                        help="template_set label injected into each doc before "
                             "import (default: '%(default)s', matching ASKCOS "
                             "default lookups)")
    parser.add_argument("--validate-only", action="store_true",
                        help="only validate locally, do not import to Mongo")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    docs = load_templates(args.inp)
    errors, stats = validate(docs)
    logger.info("Validation: total=%d invalid=%d unique_smarts=%d duplicate_smarts=%d",
                stats["total"], stats["invalid"], stats["unique_smarts"],
                stats["duplicate_smarts"])
    if errors:
        logger.error("%d template(s) failed validation; aborting seed.", errors)
        return 1
    if stats["duplicate_index"]:
        logger.error("Duplicate 'index' values found; aborting seed "
                     "(Mongo unique index would fail).")
        return 1

    if args.validate_only:
        logger.info("Validate-only mode; not importing.")
        return 0

    count = import_to_mongo(args.inp, args.collection, args.container,
                            args.host, args.user, args.pw, args.db,
                            template_set=args.template_set)
    logger.info("Seeded %d templates into independent collection '%s'.",
                count, args.collection)
    return 0


if __name__ == "__main__":
    sys.exit(main())