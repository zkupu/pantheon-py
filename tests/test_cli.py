"""Tests for CLI argument parsing, command dispatch, and command bodies."""

from unittest.mock import MagicMock, patch

import pytest

from pantheon import cli
from pantheon.agent import Event
from pantheon.gateway import Message, Usage
from pantheon.memory import FileStore, session_id
from pantheon.skill import Metadata, Skill, classify_agents


class TestArgParsing:
    def test_list_command(self):
        with patch("sys.argv", ["pantheon", "list"]), patch.object(cli, "cmd_list") as mock:
            cli.main()
            mock.assert_called_once()

    def test_ask_command(self):
        with (
            patch("sys.argv", ["pantheon", "ask", "athena", "hello", "world"]),
            patch.object(cli, "cmd_ask") as mock,
        ):
            cli.main()
            mock.assert_called_once_with("athena", "hello world")

    def test_run_command(self):
        with (
            patch("sys.argv", ["pantheon", "run", "kali", "audit", "code"]),
            patch.object(cli, "cmd_run") as mock,
        ):
            cli.main()
            mock.assert_called_once_with("kali", "audit code")

    def test_team_command(self):
        with (
            patch("sys.argv", ["pantheon", "team", "freya", "do", "stuff"]),
            patch.object(cli, "cmd_team") as mock,
        ):
            cli.main()
            mock.assert_called_once_with("freya", "do stuff")

    def test_pipe_command(self):
        with (
            patch("sys.argv", ["pantheon", "pipe", "a,b,c", "go"]),
            patch.object(cli, "cmd_pipe") as mock,
        ):
            cli.main()
            mock.assert_called_once_with("a,b,c", "go")

    def test_review_command(self):
        with (
            patch("sys.argv", ["pantheon", "review", "a,b,c", "check"]),
            patch.object(cli, "cmd_review") as mock,
        ):
            cli.main()
            mock.assert_called_once_with("a,b,c", "check")

    def test_no_command_opens_warroom(self):
        with patch("sys.argv", ["pantheon"]), patch.object(cli, "cmd_warroom") as mock:
            cli.main()
            mock.assert_called_once()


class TestCmdList:
    def test_list_outputs_table(self, capsys):
        skill = Skill(
            name="test",
            description="Testing",
            body="You are test.",
            path="/test/SKILL.md",
            metadata=Metadata(
                persona="Test Persona",
                model="test-model",
                tools=["read_file"],
                delegates=[],
            ),
        )
        with patch.object(cli.skill_mod, "discover", return_value=[skill]):
            cli.cmd_list()
        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "The Pantheon" in captured.out

    def test_list_uses_skill_discovery_not_agents(self):
        skill = Skill(
            name="athena",
            description="Architecture",
            body="You are athena.",
            path="/test/athena/SKILL.md",
            metadata=Metadata(persona="Athena", model="test-model"),
        )
        with patch.object(cli.skill_mod, "discover", return_value=[skill]) as mock_discover:
            cli.cmd_list()
            mock_discover.assert_called_once()


class TestGetAgent:
    def test_found(self):
        agents = {"athena": MagicMock()}
        result = cli._get(agents, "athena")
        assert result is agents["athena"]

    def test_not_found_exits(self):
        with pytest.raises(SystemExit):
            cli._get({}, "missing")


class TestAgentLoading:
    def test_agents_exit_cleanly_when_api_key_is_missing(self):
        with (
            patch.object(cli, "_client", side_effect=ValueError("API key is required")),
            patch.object(cli.console, "print") as mock_print,
            pytest.raises(SystemExit),
        ):
            cli._agents()

        assert "API key is required" in mock_print.call_args[0][0]


class TestEquip:
    def test_equip_registers_tools(self, tmp_agent):
        agent = tmp_agent(tools=["read_file", "write_file"])
        cli._equip(agent)
        assert agent.tools.get("read_file") is not None
        assert agent.tools.get("write_file") is not None


class TestEventHandler:
    def test_tool_call_event(self, capsys):
        e = Event(kind="tool_call", agent="test", tool="read_file", content='{"path":"x"}')
        cli._event_handler(e)
        captured = capsys.readouterr()
        assert "read_file" in captured.err

    def test_error_event(self, capsys):
        e = Event(kind="error", agent="test", content="something broke")
        cli._event_handler(e)
        captured = capsys.readouterr()
        assert "something broke" in captured.err

    def test_reply_event_with_usage(self, capsys):
        e = Event(
            kind="reply",
            agent="test",
            content="done",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )
        cli._event_handler(e)
        captured = capsys.readouterr()
        assert "150" in captured.err

    def test_tool_call_truncates_long_content(self, capsys):
        e = Event(kind="tool_call", agent="test", tool="shell_exec", content="x" * 200)
        cli._event_handler(e)
        captured = capsys.readouterr()
        assert "..." in captured.err
        assert "shell_exec" in captured.err

    def test_reply_without_tokens_is_noop(self, capsys):
        e = Event(kind="reply", agent="test", content="done", usage=Usage())
        cli._event_handler(e)
        captured = capsys.readouterr()
        assert captured.err == ""


class TestCmdAsk:
    def test_ask_sends_message(self, tmp_agent):
        agent = tmp_agent("athena", reply="wisdom")
        with patch.object(cli, "_agents", return_value={"athena": agent}):
            cli.cmd_ask("athena", "hello")
            assert agent.client.chat_stream.called or agent.client.chat_stream_full.called


class TestCmdChat:
    def test_chat_restores_saved_history(self, tmp_agent, tmp_path):
        agent = tmp_agent("athena", reply="wisdom")
        sid = session_id("athena", "interactive")
        store = FileStore(tmp_path)
        saved = [
            Message(role="system", content="You are athena."),
            Message(role="user", content="hello"),
            Message(role="assistant", content="welcome back"),
        ]
        store.save(sid, saved)

        with (
            patch.object(cli, "_agents", return_value={"athena": agent}),
            patch.object(cli.config, "memory_dir", return_value=str(tmp_path)),
            patch("builtins.input", side_effect=["/quit"]),
        ):
            cli.cmd_chat("athena")

        assert [m.role for m in agent.history] == ["system", "user", "assistant"]
        assert agent.history[1].content == "hello"
        assert agent.history[2].content == "welcome back"


class TestCmdRun:
    def test_run_executes_react_loop(self, tmp_agent):
        agent = tmp_agent("kali", reply="audit done", tools=["read_file"])
        with patch.object(cli, "_agents", return_value={"kali": agent}):
            cli.cmd_run("kali", "audit this")

        agent.client.chat.assert_called()
        messages = agent.client.chat.call_args.kwargs["messages"]
        assert any(m.content == "audit this" for m in messages if m.role == "user")


class TestCmdTeam:
    def test_team_with_delegates(self, tmp_agent):
        coord = tmp_agent("freya", reply="coordinated", delegates=["kali"])
        kali = tmp_agent("kali", reply="finding")
        agents = {"freya": coord, "kali": kali}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_team("freya", "review security")

        coord.client.chat.assert_called()
        messages = coord.client.chat.call_args.kwargs["messages"]
        assert any("review security" in m.content for m in messages if m.role == "user")

    def test_team_warns_missing_delegate(self, tmp_agent, capsys):
        coord = tmp_agent("freya", reply="done", delegates=["missing"])
        agents = {"freya": coord}

        with patch.object(cli, "_agents", return_value=agents), pytest.raises(SystemExit):
            cli.cmd_team("freya", "go")

        captured = capsys.readouterr()
        assert "missing" in captured.err

    def test_team_no_delegates_exits(self, tmp_agent):
        coord = tmp_agent("freya", reply="done", delegates=[])
        with (
            patch.object(cli, "_agents", return_value={"freya": coord}),
            pytest.raises(SystemExit),
        ):
            cli.cmd_team("freya", "go")


class TestCmdPipe:
    def test_pipe_runs_stages(self, tmp_agent):
        a1 = tmp_agent("stage1", reply="from-1")
        a2 = tmp_agent("stage2", reply="from-2")
        agents = {"stage1": a1, "stage2": a2}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_pipe("stage1,stage2", "start")

        a1.client.chat.assert_called()
        a2.client.chat.assert_called()
        a1_messages = a1.client.chat.call_args.kwargs["messages"]
        assert any(m.content == "start" for m in a1_messages if m.role == "user")


class TestCmdReview:
    def test_review_runs_fan_out(self, tmp_agent):
        r1 = tmp_agent("kali", reply="secure")
        r2 = tmp_agent("themis", reply="tested")
        synth = tmp_agent("athena", reply="all good")
        agents = {"kali": r1, "themis": r2, "athena": synth}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_review("kali,themis,athena", "review this")

        r1.client.chat.assert_called()
        r2.client.chat.assert_called()
        synth.client.chat.assert_called()

    def test_review_requires_at_least_two_agents(self):
        with patch.object(cli, "_agents") as mock_agents:
            mock_agents.return_value = {"a": MagicMock()}
            with pytest.raises(SystemExit):
                cli.cmd_review("a", "check")


class TestClassifyAgents:
    def _skills(self):
        return {
            "kali": Skill(
                name="kali",
                description="Security protector",
                body="",
                path="/test/kali/SKILL.md",
                metadata=Metadata(
                    routing_signals=["security", "vulnerability", "threat model"],
                ),
            ),
            "themis": Skill(
                name="themis",
                description="Test guardian",
                body="",
                path="/test/themis/SKILL.md",
                metadata=Metadata(
                    routing_signals=["test", "testing", "coverage", "quality gate"],
                ),
            ),
            "nuwa": Skill(
                name="nuwa",
                description="Python creator",
                body="",
                path="/test/nuwa/SKILL.md",
                metadata=Metadata(
                    routing_signals=["python", "data science", "automation"],
                ),
            ),
            "demeter": Skill(
                name="demeter",
                description="Default right hand executor",
                body="",
                path="/test/demeter/SKILL.md",
                metadata=Metadata(
                    routing_signals=["general task", "quick fix"],
                ),
            ),
        }

    def test_single_match(self):
        result = classify_agents("audit for security issues", self._skills())
        names = [n for n, _ in result]
        assert "kali" in names

    def test_multi_match(self):
        result = classify_agents("run testing for security vulnerability", self._skills())
        names = [n for n, _ in result]
        assert "kali" in names
        assert "themis" in names

    def test_no_match_returns_empty(self):
        result = classify_agents("deploy to kubernetes", self._skills())
        assert result == []

    def test_higher_score_first(self):
        result = classify_agents("test the testing coverage", self._skills())
        assert result[0][0] == "themis"
        assert result[0][1] >= 2

    def test_fallback_to_description_keywords(self):
        skills = {
            "plain": Skill(
                name="plain",
                description="Handles python automation tasks",
                body="",
                path="/test/plain/SKILL.md",
                metadata=Metadata(),
            ),
        }
        result = classify_agents("python automation", skills)
        assert len(result) == 1
        assert result[0][0] == "plain"

    def test_word_boundary_prevents_false_positives(self):
        """'test' should not match 'latest' or 'contest'."""
        result = classify_agents("the latest contest results", self._skills())
        names = [n for n, _ in result]
        assert "themis" not in names

    def test_word_boundary_matches_at_boundaries(self):
        """'test' should match when at word boundaries."""
        result = classify_agents("run the test suite", self._skills())
        names = [n for n, _ in result]
        assert "themis" in names

    def test_dot_prefix_signals_match(self):
        """Signals like '.py file' should match despite starting with non-word char."""
        skills = {
            "nuwa": Skill(
                name="nuwa",
                description="Python creator",
                body="",
                path="/test/nuwa/SKILL.md",
                metadata=Metadata(
                    routing_signals=[".py file", "python"],
                ),
            ),
        }
        result = classify_agents("fix the .py file imports", skills)
        names = [n for n, _ in result]
        assert "nuwa" in names

    def test_dot_prefix_does_not_match_inside_words(self):
        """'.py' should not match 'copy' or 'happy'."""
        skills = {
            "nuwa": Skill(
                name="nuwa",
                description="Python creator",
                body="",
                path="/test/nuwa/SKILL.md",
                metadata=Metadata(
                    routing_signals=[".py file"],
                ),
            ),
        }
        result = classify_agents("copy happy files", skills)
        assert result == []


class TestCmdAuto:
    def test_auto_arg_parsing(self):
        with (
            patch("sys.argv", ["pantheon", "auto", "review", "security"]),
            patch.object(cli, "cmd_auto") as mock,
        ):
            cli.main()
            mock.assert_called_once()

    def test_auto_dry_run_no_execute(self, tmp_agent):
        agent = tmp_agent("kali", reply="audit", tools=["read_file"], routing_signals=["security"])
        demeter = tmp_agent("demeter", reply="synthesized")
        agents = {"kali": agent, "demeter": demeter}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_auto("review security issues", lead="demeter", dry_run=True)

        assert not agent.client.chat.called

    def test_auto_single_agent_runs_directly(self, tmp_agent):
        agent = tmp_agent(
            "kali",
            reply="audit done",
            tools=["read_file"],
            routing_signals=["security"],
        )
        demeter = tmp_agent("demeter", reply="ok")
        agents = {"kali": agent, "demeter": demeter}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_auto("check security", lead="demeter", dry_run=False)

        assert agent.client.chat.called

    def test_auto_no_match_falls_back_to_lead(self, tmp_agent):
        demeter = tmp_agent(
            "demeter",
            reply="handled",
            tools=["read_file"],
            routing_signals=["general task"],
        )
        agents = {"demeter": demeter}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_auto("do something unknown", lead="demeter", dry_run=False)

        assert demeter.client.chat.called

    def test_auto_multi_agent_dispatches_review(self, tmp_agent):
        kali = tmp_agent("kali", reply="secure", tools=["read_file"], routing_signals=["security"])
        themis = tmp_agent("themis", reply="tested", tools=["read_file"], routing_signals=["test"])
        demeter = tmp_agent("demeter", reply="synthesized", tools=["read_file"])
        agents = {"kali": kali, "themis": themis, "demeter": demeter}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_auto("test security", lead="demeter", dry_run=False)

        assert kali.client.chat.called
        assert themis.client.chat.called
        assert demeter.client.chat.called

    def test_auto_multi_agent_dry_run_shows_topology(self, tmp_agent, capsys):
        kali = tmp_agent("kali", reply="secure", tools=["read_file"], routing_signals=["security"])
        themis = tmp_agent("themis", reply="tested", tools=["read_file"], routing_signals=["test"])
        demeter = tmp_agent("demeter", reply="ok")
        agents = {"kali": kali, "themis": themis, "demeter": demeter}

        with patch.object(cli, "_agents", return_value=agents):
            cli.cmd_auto("test security", lead="demeter", dry_run=True)

        captured = capsys.readouterr()
        assert "Auto-routing plan" in captured.err
        assert not kali.client.chat.called
        assert not themis.client.chat.called


class TestWarRoom:
    def test_list_then_quit(self, tmp_agent):
        agents = {
            "athena": tmp_agent("athena", reply="wisdom"),
            "eris": tmp_agent("eris", reply="chaos"),
        }

        with (
            patch.object(cli, "_agents", return_value=agents),
            patch("builtins.input", side_effect=["/list", "/quit"]),
        ):
            cli.cmd_warroom()

    def test_broadcast_collects_all_replies(self, tmp_agent):
        agents = {
            "athena": tmp_agent("athena", reply="wisdom"),
            "eris": tmp_agent("eris", reply="chaos"),
        }

        with (
            patch.object(cli, "_agents", return_value=agents),
            patch("builtins.input", side_effect=["/all hello", "/quit"]),
        ):
            cli.cmd_warroom()

        assert agents["athena"].client.chat.called
        assert agents["eris"].client.chat.called
