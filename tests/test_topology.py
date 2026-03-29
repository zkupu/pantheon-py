"""Tests for adaptive topology selection and execution."""

import pytest

from pantheon.agent import DeadlineExceededError
from pantheon.orchestrate import (
    TaskNode,
    Topology,
    run_topology,
    select_topology,
)


class TestSelectTopology:
    def test_empty_tasks(self):
        assert select_topology([]) == Topology.PARALLEL

    def test_all_independent(self):
        tasks = [TaskNode(id=f"t{i}", agent=f"a{i}") for i in range(5)]
        assert select_topology(tasks) == Topology.PARALLEL

    def test_fully_sequential(self):
        tasks = [
            TaskNode(id="t0", agent="a"),
            TaskNode(id="t1", agent="b", depends_on=["t0"]),
            TaskNode(id="t2", agent="c", depends_on=["t1"]),
            TaskNode(id="t3", agent="d", depends_on=["t2"]),
            TaskNode(id="t4", agent="e", depends_on=["t3"]),
        ]
        assert select_topology(tasks) == Topology.SEQUENTIAL

    def test_hierarchical_deep_chain_multiple_agents(self):
        tasks = [
            TaskNode(id="t0", agent="a"),
            TaskNode(id="t1", agent="b", depends_on=["t0"]),
            TaskNode(id="t2", agent="c", depends_on=["t1"]),
            TaskNode(id="t3", agent="a", depends_on=["t2"]),
        ]
        result = select_topology(tasks)
        assert result in (Topology.HIERARCHICAL, Topology.HYBRID)

    def test_hybrid_partial_parallelism(self):
        tasks = [
            TaskNode(id="t0", agent="a"),
            TaskNode(id="t1", agent="b"),
            TaskNode(id="t2", agent="c", depends_on=["t0"]),
            TaskNode(id="t3", agent="d", depends_on=["t1"]),
        ]
        result = select_topology(tasks)
        assert result == Topology.HYBRID

    def test_single_task(self):
        tasks = [TaskNode(id="t0", agent="a")]
        assert select_topology(tasks) == Topology.PARALLEL

    def test_two_independent(self):
        tasks = [
            TaskNode(id="t0", agent="a"),
            TaskNode(id="t1", agent="b"),
        ]
        assert select_topology(tasks) == Topology.PARALLEL

    def test_shared_ancestor_depth_counts_full_longest_path(self):
        tasks = [
            TaskNode(id="t0", agent="a"),
            TaskNode(id="t1", agent="b", depends_on=["t0"]),
            TaskNode(id="t_extra", agent="f"),
            TaskNode(id="t2", agent="c", depends_on=["t0"]),
            TaskNode(id="t3", agent="d", depends_on=["t2"]),
            TaskNode(id="t4", agent="e", depends_on=["t1", "t3"]),
        ]
        assert select_topology(tasks) == Topology.HIERARCHICAL


class TestRunTopology:
    def test_parallel(self, tmp_agent):
        lead = tmp_agent("lead", reply="synthesized")
        agents = {
            "a": tmp_agent("a", reply="result-a"),
            "b": tmp_agent("b", reply="result-b"),
        }
        tasks = [
            TaskNode(id="t0", agent="a", description="do A"),
            TaskNode(id="t1", agent="b", description="do B"),
        ]

        result = run_topology(Topology.PARALLEL, lead, agents, tasks)
        assert result == "synthesized"

    def test_sequential(self, tmp_agent):
        lead = tmp_agent("lead")
        agents = {
            "a": tmp_agent("a", reply="from-a"),
            "b": tmp_agent("b", reply="from-b"),
        }
        tasks = [
            TaskNode(id="t0", agent="a", description="step 1"),
            TaskNode(id="t1", agent="b", description="step 2", depends_on=["t0"]),
        ]

        result = run_topology(Topology.SEQUENTIAL, lead, agents, tasks)
        assert result == "from-b"

    def test_hierarchical(self, tmp_agent):
        lead = tmp_agent("lead", reply="team result")
        agents = {"a": tmp_agent("a", reply="spec-a")}
        tasks = [TaskNode(id="t0", agent="a", description="work")]

        result = run_topology(Topology.HIERARCHICAL, lead, agents, tasks)
        assert result == "team result"

    def test_hybrid(self, tmp_agent):
        lead = tmp_agent("lead", reply="hybrid result")
        agents = {"a": tmp_agent("a", reply="r-a"), "b": tmp_agent("b", reply="r-b")}
        tasks = [
            TaskNode(id="t0", agent="a", description="parallel"),
            TaskNode(id="t1", agent="b", description="depends", depends_on=["t0"]),
        ]

        result = run_topology(Topology.HYBRID, lead, agents, tasks)
        assert result == "hybrid result"

    def test_missing_agent(self, tmp_agent):
        lead = tmp_agent("lead", reply="ok")
        tasks = [TaskNode(id="t0", agent="missing", description="fail")]
        result = run_topology(Topology.PARALLEL, lead, {}, tasks)
        assert "ok" in result  # lead synthesizes even with errors

    def test_sequential_deadline_exceeded(self, tmp_agent):
        lead = tmp_agent("lead")
        agents = {"a": tmp_agent("a", reply="r-a")}
        tasks = [TaskNode(id="t0", agent="a", description="step 1")]

        with pytest.raises(DeadlineExceededError, match="sequential topology"):
            run_topology(Topology.SEQUENTIAL, lead, agents, tasks, deadline_s=0.0)

    def test_hybrid_deadline_sequential_phase(self, tmp_agent):
        lead = tmp_agent("lead", reply="hybrid result")
        agents = {"a": tmp_agent("a", reply="r-a"), "b": tmp_agent("b", reply="r-b")}
        tasks = [
            TaskNode(id="t0", agent="a", description="parallel"),
            TaskNode(id="t1", agent="b", description="depends", depends_on=["t0"]),
        ]

        with pytest.raises(DeadlineExceededError):
            run_topology(Topology.HYBRID, lead, agents, tasks, deadline_s=0.0)

    def test_run_topology_accepts_deadline(self, tmp_agent):
        """Verify deadline_s parameter is accepted and passed through."""
        lead = tmp_agent("lead", reply="synthesized")
        agents = {"a": tmp_agent("a", reply="result-a")}
        tasks = [TaskNode(id="t0", agent="a", description="do A")]

        result = run_topology(Topology.PARALLEL, lead, agents, tasks, deadline_s=600.0)
        assert result == "synthesized"
