"""Mock providers, tool handlers, and committee coordinator for the Eval Harness.

These fixtures let the :class:`EvalRunner` replay golden sets without touching
real LLM, tool, or committee infrastructure. All responses are deterministic
so eval results are reproducible across runs.

Each mock accepts the same shape of input the real component would receive
and returns a dict shaped like the real component's output, so scorers can
operate uniformly on ``result["output"]``.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _lattice_determinant(lattice: list[list[float]]) -> float:
    """Compute the determinant of a 3x3 lattice matrix."""
    if len(lattice) != 3 or any(len(row) != 3 for row in lattice):
        return 0.0
    a, b, c = lattice
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def _min_interatomic_distance(coords: list[list[float]], lattice: list[list[float]]) -> float:
    """Approximate minimum interatomic distance under periodic boundary conditions.

    Uses a reduced-coordinate image search within [-1, 1] translations. Good
    enough for the golden set's overlap cases (atoms at 0.1,0.1,0.1 vs 0,0,0).
    """
    if len(coords) < 2:
        return float("inf")
    min_dist = float("inf")
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            for nx in (-1, 0, 1):
                for ny in (-1, 0, 1):
                    for nz in (-1, 0, 1):
                        d = 0.0
                        for k in range(3):
                            diff = coords[i][k] - coords[j][k] + (nx, ny, nz)[k]
                            d += diff * diff * (
                                (lattice[k][k] if k < len(lattice) and k < len(lattice[k]) else 1.0) ** 2
                            )
                        # Take sqrt of the summed scaled diffs
                        dist = math.sqrt(d)
                        if dist < min_dist:
                            min_dist = dist
    return min_dist


# ──────────────────────────────────────────────────────────────────────────
# MockLLMProvider
# ──────────────────────────────────────────────────────────────────────────

class MockLLMProvider:
    """Returns canned responses for crystal structure generation requests.

    Implements a lightweight ``complete`` method compatible in spirit with the
    real :class:`LLMProvider` protocol. When the prompt looks like a crystal
    generation request (carries a ``structure`` payload or a ``species`` list),
    the mock emits a deterministic candidate structure; otherwise it echoes a
    canned text response.
    """

    def __init__(self, model: str = "mock-llm-v1"):
        self.model = model
        self.call_count = 0

    async def complete(self, request: dict | Any) -> dict:
        """Return a canned chat completion.

        Accepts either a dict-like request with ``messages`` or a plain dict
        with a ``prompt``/``structure`` key. Returns a dict shaped like
        ``ChatResponse.model_dump()``.
        """
        self.call_count += 1
        prompt_text = self._extract_prompt(request)
        payload = self._try_parse_payload(prompt_text)

        # Crystal generation: echo the input structure when present so the
        # mock faithfully replays what the target received. Falls back to
        # building a simple cubic structure from species/lattice otherwise.
        if isinstance(payload, dict) and ("structure" in payload or "species" in payload):
            if "structure" in payload and isinstance(payload["structure"], dict):
                structure = payload["structure"]
            else:
                species = payload.get("species") or ["Si", "Si"]
                lattice = payload.get("lattice", [[5.0, 0, 0], [0, 5.0, 0], [0, 0, 5.0]])
                structure = {
                    "lattice": lattice,
                    "coords": [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]][: len(species)],
                    "species": species,
                }
            content = json.dumps({
                "candidate": structure,
                "rationale": "mock deterministic candidate",
                "model": self.model,
            })
        else:
            content = f"mock response from {self.model}: {prompt_text[:200]}"

        return {
            "content": content,
            "tool_calls": [],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
            "model": self.model,
            "request_id": f"mock-req-{self.call_count}",
        }

    async def healthcheck(self) -> dict:
        return {"status": "healthy", "message": "mock provider always healthy", "latency_ms": 1}

    @staticmethod
    def _extract_prompt(request: Any) -> str:
        if isinstance(request, dict):
            messages = request.get("messages")
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if isinstance(last, dict):
                    return str(last.get("content", ""))
            return str(request.get("prompt", "") or request.get("structure", ""))
        # Pydantic model
        for attr in ("messages", "prompt"):
            value = getattr(request, attr, None)
            if value:
                if isinstance(value, list) and value:
                    last = value[-1]
                    return getattr(last, "content", str(last))
                return str(value)
        return str(request)

    @staticmethod
    def _try_parse_payload(text: str) -> dict | None:
        if not text:
            return None
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return None
        return None


# ──────────────────────────────────────────────────────────────────────────
# MockToolHandler
# ──────────────────────────────────────────────────────────────────────────

class MockToolHandler:
    """Returns canned results for tools used by the eval golden sets.

    Recognized tools:
      * ``pymatgen_validate`` — runs a lightweight structural validity check
        (lattice determinant, atomic distances, stoichiometry) and returns
        ``{"valid": bool, "reason": str | None, "spacegroup": int | None}``.
      * ``dft_submit`` — returns a mock DFT job id without performing any
        computation.
      * ``m3gnet_relax`` / ``m3gnet_predict`` — return canned relaxation /
        property prediction payloads.
    """

    SUPPORTED_TOOLS: frozenset[str] = frozenset({
        "pymatgen_validate",
        "dft_submit",
        "dft_vasp",
        "dft_quantum_espresso",
        "m3gnet_relax",
        "m3gnet_predict",
    })

    def __init__(self):
        self.call_log: list[dict] = []

    async def invoke(self, tool_name: str, arguments: dict) -> dict:
        """Invoke a mock tool and return a result dict.

        The returned dict always carries ``tool``, ``status``, ``output`` and
        ``provenance`` keys, matching the shape scorers expect.
        """
        self.call_log.append({"tool": tool_name, "arguments": arguments})
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return self._unknown_tool(tool_name, arguments)
        output = handler(arguments)
        return {
            "tool": tool_name,
            "status": "success",
            "output": output,
            "provenance": {"mock": True, "tool": tool_name},
        }

    # ── tool implementations ─────────────────────────────────────────────

    def _tool_pymatgen_validate(self, arguments: dict) -> dict:
        structure = arguments.get("structure") or {}
        lattice = structure.get("lattice") or []
        coords = structure.get("coords") or []
        species = structure.get("species") or []

        # Singular lattice (zero determinant).
        det = _lattice_determinant(lattice)
        if abs(det) < 1e-9:
            return {"valid": False, "reason": "singular_lattice", "spacegroup": None}

        # Overlapping atoms.
        min_dist = _min_interatomic_distance(coords, lattice)
        if min_dist < 0.5:
            return {"valid": False, "reason": "atoms_too_close", "spacegroup": None}

        # Stoichiometry check: a diamond-like structure expects an even count
        # of a single element. Two different species in a 2+1 arrangement is
        # treated as a stoichiometry error (matches golden case crystal_004).
        if len(set(species)) > 1 and len(species) == 3:
            return {"valid": False, "reason": "stoichiometry_error", "spacegroup": None}

        # Otherwise valid; assign spacegroup 227 (Fd-3m) for cubic diamond-like.
        return {"valid": True, "reason": None, "spacegroup": 227}

    def _tool_dft_submit(self, arguments: dict) -> dict:
        structure_hash = hashlib.sha256(
            json.dumps(arguments.get("structure", {}), sort_keys=True).encode()
        ).hexdigest()[:16]
        return {
            "job_id": f"mock-dft-{len(self.call_log):04d}",
            "status": "queued",
            "structure_hash": structure_hash,
        }

    def _tool_dft_vasp(self, arguments: dict) -> dict:
        return self._tool_dft_submit(arguments)

    def _tool_dft_quantum_espresso(self, arguments: dict) -> dict:
        return self._tool_dft_submit(arguments)

    def _tool_m3gnet_relax(self, arguments: dict) -> dict:
        structure = arguments.get("structure") or {}
        return {
            "relaxed_structure": structure,
            "energy": -10.42,
            "forces_max": 0.001,
            "converged": True,
        }

    def _tool_m3gnet_predict(self, arguments: dict) -> dict:
        return {
            "formation_energy_per_atom": -0.5,
            "bulk_modulus": 98.5,
            "shear_modulus": 47.2,
            "confidence": 0.82,
        }

    def _unknown_tool(self, tool_name: str, arguments: dict) -> dict:
        return {
            "tool": tool_name,
            "status": "error",
            "error": f"unknown_tool: {tool_name}",
            "output": {},
            "provenance": {"mock": True},
        }


# ──────────────────────────────────────────────────────────────────────────
# MockCommitteeCoordinator
# ──────────────────────────────────────────────────────────────────────────

class MockCommitteeCoordinator:
    """Returns canned committee verdicts.

    The mock mirrors the real ``CommitteeCoordinator``'s output shape: a dict
    with ``decision`` (``pass``/``reject``/``request_evidence``/
    ``human_review``), ``scorecard``, ``blocking_reasons`` and ``warnings``.
    Verdicts are derived deterministically from the input so the eval is
    reproducible.
    """

    def __init__(self, default_decision: str = "pass"):
        self.default_decision = default_decision
        self.verdict_count = 0

    async def assess(self, case_input: dict) -> dict:
        """Return a canned verdict for a committee case.

        ``case_input`` may carry any of:
          * ``committee_type`` — ``crystal_construction`` / ``candidate_priority``
            / ``deviation_review`` / ``external_evidence``.
          * ``structure`` — crystal payload; if invalid, the verdict is
            ``reject``.
          * ``evidence`` — list of evidence items; an item with
            ``consistent=False`` triggers a reject for external_evidence.
        """
        self.verdict_count += 1
        committee_type = case_input.get("committee_type", "crystal_construction")

        blocking_reasons: list[str] = []
        warnings: list[str] = []
        score = 0.85
        decision = self.default_decision

        # Crystal construction: delegate to the mock validator.
        if committee_type == "crystal_construction" and "structure" in case_input:
            handler = MockToolHandler()
            validation = handler._tool_pymatgen_validate({"structure": case_input["structure"]})
            if not validation.get("valid"):
                blocking_reasons.append(f"structure_invalid: {validation.get('reason')}")
                decision = "reject"
                score = 0.0

        # External evidence: any inconsistent evidence item forces rejection.
        if committee_type == "external_evidence":
            evidence = case_input.get("evidence") or []
            inconsistent = [e for e in evidence if isinstance(e, dict) and e.get("consistent") is False]
            if inconsistent:
                blocking_reasons.append("hard_rule_conflict")
                decision = "reject"
                score = 0.0

        # Candidate priority: a small score signals request_evidence.
        if committee_type == "candidate_priority" and score < 0.7 and not blocking_reasons:
            decision = "request_evidence"
            warnings.append("low_confidence_ranking")

        return {
            "verdict_id": f"mock-verdict-{self.verdict_count:04d}",
            "decision": decision,
            "scorecard": {"score": round(score, 4), "passed": decision == "pass"},
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "required_actions": [] if decision == "pass" else ["review_findings"],
            "verifier_provenance": {"method": "mock", "committee_type": committee_type},
        }
