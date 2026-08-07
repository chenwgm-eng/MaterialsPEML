#!/usr/bin/env python3
"""MPA (Material Property Axiom) prediction client.

Predict molecular properties from SMILES via a configured MPA HTTP service.
Supports multiple molecules AND multiple properties in one invocation.  The
service accepts only one property per request, so this client loops over the
requested properties and aggregates the results into a molecule × property
matrix.

Usage:
    python mpa_predict.py --property BP_K --smiles "CCO" "c1ccccc1"
    python mpa_predict.py --property BP_K flash_point_K --smiles "CCO" "Cc1ccccc1"
    python mpa_predict.py --list-properties
    python mpa_predict.py --property BP_K --smiles "CCO" --output result.json

Standard library only (urllib + json + argparse) — no third-party deps.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration — read once at import time
# ---------------------------------------------------------------------------
_BASE_URL: str = os.environ.get("MPA_BASE_URL", "").rstrip("/")
_API_TOKEN: str = os.environ.get("MPA_API_TOKEN", "")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_TIMEOUT: int = 120          # seconds per request
_DEFAULT_NUM_CONFS: int = 1
_DEFAULT_BATCH_SIZE: int = 8
_MAX_RETRIES: int = 2                # transient failures only
_RETRY_BACKOFF: float = 2.0          # exponential backoff multiplier
_RETRYABLE_STATUSES: Tuple[int, ...] = (429, 500, 502, 503, 504)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MPAError(Exception):
    """Base for all client-side or relayed service errors."""


class MPAConfigError(MPAError):
    """Missing environment configuration (BASE_URL / API_TOKEN)."""


class MPANetworkError(MPAError):
    """Unrecoverable network / DNS / TLS failure."""


class MPAServiceError(MPAError):
    """Service returned a non-retryable HTTP error (4xx except 429)."""

# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _check_config() -> None:
    """Raise MPAConfigError when required env vars are absent."""
    if not _BASE_URL or not _API_TOKEN:
        raise MPAConfigError(
            "MPA_BASE_URL and MPA_API_TOKEN are required for the standalone "
            "client. In managed Mira chats, use the mira_inference_call tool."
        )


def _build_request(
    path: str,
    method: str = "GET",
    payload: Optional[dict] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> urllib.request.Request:
    """Construct an HTTP request with auth and content-type headers."""
    url = _BASE_URL + path
    data: Optional[bytes] = None
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_API_TOKEN}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    # attach timeout to the request object for urlopen pick-up
    req.timeout = timeout  # type: ignore[attr-defined]
    return req


def _execute_request(req: urllib.request.Request) -> dict:
    """Send the request and parse the JSON body.  Transient retries are handled
    at the caller level (see ``_request_with_retry``)."""
    try:
        with urllib.request.urlopen(req, timeout=getattr(req, "timeout", _DEFAULT_TIMEOUT)) as resp:
            body = resp.read().decode()
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        code = exc.code
        if code in _RETRYABLE_STATUSES:
            raise MPAServiceError(f"HTTP {code} (retryable): {body}") from exc
        raise MPAServiceError(f"HTTP {code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise MPANetworkError(f"Network error: {exc.reason}") from exc


def _is_retryable(exc: MPAError) -> bool:
    """Return True when the error is likely transient."""
    if isinstance(exc, MPANetworkError):
        return True
    if isinstance(exc, MPAServiceError):
        return any(str(status) in str(exc) for status in ("429", "500", "502", "503", "504"))
    return False


def _request_with_retry(
    path: str,
    method: str = "GET",
    payload: Optional[dict] = None,
    timeout: int = _DEFAULT_TIMEOUT,
    max_retries: int = _MAX_RETRIES,
) -> dict:
    """Send request with exponential-backoff retry for transient failures."""
    _check_config()
    last_exc: Optional[MPAError] = None
    for attempt in range(max_retries + 1):
        try:
            req = _build_request(path, method, payload, timeout)
            return _execute_request(req)
        except (MPAServiceError, MPANetworkError) as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            wait = _RETRY_BACKOFF ** (attempt + 1)
            time.sleep(wait)
    # Should be unreachable, but guard defensively
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_properties() -> dict:
    """Return the set of supported property names from the service metadata."""
    return _request_with_retry("/api/v1/properties")


def predict_one(
    property_name: str,
    smiles: List[str],
    num_confs: int = _DEFAULT_NUM_CONFS,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict:
    """Predict a single property for one or more molecules.

    Parameters
    ----------
    property_name : str
        Exact property name, e.g. ``"BP_K"``.
    smiles : list[str]
        One or more SMILES strings.
    num_confs : int
        3-D conformers generated per molecule (default 1).
    batch_size : int
        Inference batch size (default 8).

    Returns
    -------
    dict
        Service response; ``prediction_list`` holds predictions in the same
        order as *smiles*.
    """
    payload: Dict[str, Any] = {
        "property_name": property_name,
        "smiles": smiles,
        "num_confs": num_confs,
        "batch_size": batch_size,
    }
    return _request_with_retry("/api/v1/predict", method="POST", payload=payload)


def predict(
    properties: List[str],
    smiles: List[str],
    num_confs: int = _DEFAULT_NUM_CONFS,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Predict every requested property for every molecule.

    One bad property does not abort the batch — it is recorded under
    ``errors``.  ``predictions[prop][i]`` aligns with ``smiles[i]``.

    Returns
    -------
    (output_dict, errors_dict)
    """
    predictions: Dict[str, Optional[list]] = {}
    errors: Dict[str, str] = {}
    total = len(properties)
    for idx, prop in enumerate(properties, 1):
        if verbose:
            print(f"[{idx}/{total}] predicting {prop} ...", file=sys.stderr)
        try:
            res = predict_one(prop, smiles, num_confs, batch_size)
            predictions[prop] = res.get("prediction_list")
            if verbose:
                print(f"      {prop}: ok", file=sys.stderr)
        except MPAError as exc:
            errors[prop] = str(exc)
            if verbose:
                print(f"      {prop}: FAILED — {exc}", file=sys.stderr)

    out: Dict[str, Any] = {
        "smiles_list": smiles,
        "properties": properties,
        "predictions": predictions,
    }
    if errors:
        out["errors"] = errors
    return out, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _validate_positive_int(value: str) -> int:
    """argparse type callable — reject non-positive integers."""
    ival = int(value)
    if ival <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
    return ival


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="MPA (Material Property Axiom) molecular property prediction client",
    )
    parser.add_argument(
        "--property",
        dest="properties",
        nargs="+",
        help="one or more property_name values, e.g. BP_K flash_point_K",
    )
    parser.add_argument(
        "--smiles",
        nargs="+",
        help="one or more SMILES strings",
    )
    parser.add_argument(
        "--num-confs",
        type=_validate_positive_int,
        default=_DEFAULT_NUM_CONFS,
        help=f"3D conformers per molecule (default {_DEFAULT_NUM_CONFS})",
    )
    parser.add_argument(
        "--batch-size",
        type=_validate_positive_int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"inference batch size (default {_DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--list-properties",
        action="store_true",
        help="list available property_name values and exit",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="write JSON result to FILE instead of stdout",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="print per-property progress to stderr",
    )
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # --list-properties
    # ------------------------------------------------------------------
    if args.list_properties:
        try:
            payload = list_properties()
        except MPAError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    if not args.properties:
        parser.error("--property is required (or use --list-properties)")
    if not args.smiles:
        parser.error("--smiles is required")

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------
    try:
        out, errors = predict(
            properties=args.properties,
            smiles=args.smiles,
            num_confs=args.num_confs,
            batch_size=args.batch_size,
            verbose=args.verbose,
        )
    except MPAConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except MPAError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(2)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    result_json = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result_json + "\n")
        if args.verbose:
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(result_json)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
