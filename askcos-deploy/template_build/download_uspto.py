"""Download USPTO public-domain reaction data (Lowe 1976-2016).

USPTO patent reaction data is a US government work and is in the public
domain, so it is safe to use for commercial purposes.

This script fetches reaction SMILES data from a configurable source and
normalizes it into a per-line, tab-separated dataset:

    reaction_id <TAB> reactants.reagents>...>products

Supported inputs:
  * a direct URL to a plain-text rxnsmiles file (--url)
  * a direct URL to a .tar.gz archive of rxnsmiles files (--url)
  * an already-downloaded local file: .txt / .tsv / .gz / .tar.gz (--local)

Many public mirrors expose the data via Git-LFS (raw HTTP returns a small
LFS pointer, not the payload). If the download looks too small (< 1 MiB),
this script will refuse to treat it as data and tell you to use --local
with a file you retrieved via `git lfs pull` or a direct mirror.

Usage:
    python download_uspto.py --out uspto_reactions.tsv.gz
    python download_uspto.py --url <mirror-url> --out uspto_reactions.tsv.gz
    python download_uspto.py --local rxnsmiles_1976_2016.txt --out out.tsv.gz
"""

from __future__ import annotations

import argparse
import gzip
import io
import logging
import sys
import tarfile
import tempfile
from pathlib import Path

import requests

logger = logging.getLogger("download_uspto")

# A maintained public mirror of Lowe's USPTO reaction SMILES (public domain).
# Override with --url if this mirror is unavailable.
DEFAULT_URL = (
    "https://raw.githubusercontent.com/ComDec/data_for_chem/master/"
    "data/original_data/data_from_USPTO_utf8.tar.gz"
)

MIN_BYTES = 1 << 20  # 1 MiB — below this it is almost certainly an LFS pointer


def _is_gzip_name(path: str) -> bool:
    return path.endswith(".gz") or path.endswith(".tgz")


def _open_text(obj, name: str):
    """Open a raw/text or gzip stream for reading text lines."""
    if isinstance(obj, io.BytesIO) or hasattr(obj, "read"):
        raw = obj
    else:
        raw = obj  # file object
    if _is_gzip_name(name):
        return gzip.open(raw, "rt", encoding="utf-8", errors="replace")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


def parse_rxnsmiles_line(line: str, fallback_id: str = "") -> str | None:
    """Normalize a raw Lowe-format reaction line into 'reaction_id\\tSMILES'.

    Lowe's USPTO reaction SMILES format (tab-delimited):
        <ReactionSmiles>\\t<PatentNumber>\\t<ParagraphNum>\\t<Year>\\t<Yield>\\t<CalcYield>

    The ReactionSmiles uses single ``>`` separators to split three groups:
        <reactants.reagents> <catalyst> <products>
    e.g.  ``A.B>C>D``. We collapse this into the two-group form the template
    pipeline expects (``reactants>>products``) by keeping everything left of
    the first ``>`` as the reactant side and everything right of the last
    ``>`` as the product side. Atom mapping (``[Br:1]``) is preserved verbatim.

    Also accepts the older ``<id>\\t<reactants>>products>`` two-column form.

    Returns None for blank lines, header lines, or lines without a reaction.
    """
    line = line.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 2:
        return None

    # Header line: first column is the literal column name, not a reaction.
    if parts[0].startswith("ReactionSmiles"):
        return None

    first = parts[0]

    # Two-column form already normalized in the past: <id>\t<reactants>>products>
    if ">>" in first:
        return f"{parts[1].strip()}\t{first}" if fallback_id else f"{parts[0]}\t{first}"

    # Lowe single-'>' three-group form: first column is the reaction SMILES.
    if ">" in first:
        left, _, right = first.partition(">")
        # Keep only the last '>' split's right side as products (handles 3 groups).
        products = first.rsplit(">", 1)[1]
        if not products:
            return None
        # Reactant side = everything before the first '>' (reactants + reagents).
        reactants_side = left
        rxn_id = fallback_id or parts[1].strip() or "r"
        return f"{rxn_id}\t{reactants_side}>>{products}"

    return None


def _iter_lines(*streams):
    """Yield non-empty stripped lines from one or more text streams."""
    for stream in streams:
        for raw in stream:
            line = raw.strip()
            if line:
                yield line


def _archive_text_streams(buffer: io.BytesIO):
    """Yield (name, text_stream) for each member of a tar.gz archive."""
    buffer.seek(0)
    with tarfile.open(fileobj=buffer, mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name.lower()
            if not (name.endswith(".txt") or name.endswith(".smiles")
                    or name.endswith(".tsv") or name.endswith(".smi")):
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            yield member.name, _open_text(f, member.name)


def _consume_stream(streams, outfh) -> int:
    """Write normalized reaction lines; returns count written.

    `streams` iterates over text streams, or (name, text_stream) tuples.
    """
    written = 0
    for item in streams:
        stream = item[1] if isinstance(item, tuple) else item
        for line in _iter_lines(stream):
            norm = parse_rxnsmiles_line(line)
            if norm is None:
                continue
            outfh.write(norm + "\n")
            written += 1
    return written


def _open_out(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "wt", encoding="utf-8", newline="")
    return open(path, "w", encoding="utf-8", newline="")


def download(url: str, out: str) -> int:
    """Stream a URL (plain text or tar.gz) to a normalized output file."""
    logger.info("Downloading %s -> %s", url, out)
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        # Buffer the whole download in memory so we can branch on archive vs text.
        buffer = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=1 << 20):
            buffer.write(chunk)
        size = buffer.getbuffer().nbytes
        logger.info("Downloaded %d bytes", size)
        if size < MIN_BYTES:
            raise RuntimeError(
                f"Downloaded only {size} bytes — likely a Git-LFS pointer, not data. "
                "Use --local with a file obtained via 'git lfs pull' or a direct mirror."
            )
        buffer.seek(0)
        with _open_out(out) as outfh:
            if url.split("?")[0].lower().endswith((".tar.gz", ".tgz")):
                streams = _archive_text_streams(buffer)
                written = _consume_stream(streams, outfh)
            else:
                written = _consume_stream([_open_text(buffer, url)], outfh)
    logger.info("Wrote %d reactions -> %s", written, out)
    return written


def normalize_local(src: str, out: str) -> int:
    """Normalize an existing local file (text or tar.gz) to the tsv format."""
    logger.info("Normalizing %s -> %s", src, out)
    with _open_out(out) as outfh:
        if src.lower().endswith((".tar.gz", ".tgz")):
            with open(src, "rb") as f:
                data = f.read()
            streams = _archive_text_streams(io.BytesIO(data))
            written = _consume_stream(streams, outfh)
        else:
            open_fn = gzip.open if _is_gzip_name(src) else open
            if _is_gzip_name(src):
                with open_fn(src, "rt", encoding="utf-8", errors="replace") as fh:
                    written = _consume_stream([fh], outfh)
            else:
                with open_fn(src, "r", encoding="utf-8", errors="replace") as fh:
                    written = _consume_stream([fh], outfh)
    logger.info("Wrote %d reactions -> %s", written, out)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="uspto_reactions.tsv.gz")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--local", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.local:
            normalize_local(args.local, args.out)
        else:
            download(args.url, args.out)
    except (requests.RequestException, RuntimeError, tarfile.TarError) as exc:
        logger.error("Failed: %s\nTry --local <file> or --url <direct-mirror>.", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())