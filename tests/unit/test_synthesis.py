"""Tests for synthesis planning module."""

import pytest
from battery_materials_agent.synthesis.synthesis_planner import (
    SynthesisPlanner, SynthesisRoute, RouteStep,
)


class TestSynthesisPlanner:
    def setup_method(self):
        self.planner = SynthesisPlanner(askcos_url="http://localhost:9999")

    def test_plan_synthesis_demo_mode(self):
        routes = self.planner.plan_synthesis("CCO")
        assert len(routes) > 0
        assert isinstance(routes[0], SynthesisRoute)
        assert routes[0].target_smiles == "CCO"

    def test_check_feasibility(self):
        score = self.planner.check_feasibility("CCO")
        assert 0.0 <= score <= 1.0

    def test_check_feasibility_empty(self):
        with pytest.raises(ValueError):
            self.planner.check_feasibility("")

    def test_filter_synthesizable(self):
        candidates = ["CCO", "CC(=O)O", "c1ccccc1"]
        result = self.planner.filter_synthesizable(candidates, threshold=0.0)
        assert len(result) > 0

    def test_score_candidates(self):
        candidates = ["CCO", "CC(=O)O"]
        scored = self.planner.score_candidates(candidates)
        assert len(scored) == 2
        assert all(isinstance(s, tuple) for s in scored)

    def test_route_step_fields(self):
        step = RouteStep(
            reaction_smiles="A>>B",
            reactants=["A"],
            products=["B"],
            conditions="Standard",
            score=0.8,
        )
        assert step.reaction_smiles == "A>>B"
        assert step.score == 0.8

    def test_synthesis_route_fields(self):
        route = SynthesisRoute(
            target_smiles="CCO",
            steps=[RouteStep()],
            overall_score=0.8,
            num_steps=1,
            feasibility_score=0.8,
            is_feasible=True,
        )
        assert route.target_smiles == "CCO"
        assert route.is_feasible is True
