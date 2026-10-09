"""Acceptance tests for the capability ladder: task class, fallback, budgets."""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from model_router.router import (  # noqa: E402
    STRONG_UNAVAILABLE,
    ConfigError,
    State,
    invoke,
    load_config,
    normalize,
    plan,
)
from model_router.tomlutil import loads  # noqa: E402
from model_router.transport import post_chat  # noqa: E402

KEY = "unit-test-key-value"
PROMPT = "prompt-body-should-not-be-stored"
KEY_NAMES = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "CEREBRAS_API_KEY",
    "MACH_BATCH_API_KEY",
    "DEEPINFRA_API_KEY",
    "TOGETHER_API_KEY",
    "MACH_FRONTIER_API_KEY",
)

BASE = """
schema = 1

[ladder]
order = ["local", "free", "batch", "cheap", "strong"]

[tiers.local]
billable = false
fast = false
providers = ["ollama"]

[tiers.free]
billable = false
fast = true
providers = ["groq", "gemini"]

[tiers.batch]
billable = true
fast = false
non_urgent_only = true
discount = 0.5
providers = ["batch"]

[tiers.cheap]
billable = true
fast = false
providers = ["deepinfra"]

[tiers.strong]
billable = true
fast = false
providers = ["frontier"]

[providers.ollama]
model = "example-local"
base_url = "http://127.0.0.1:11434/v1"
api_key_env = ""
usd_per_call = 0

[providers.groq]
model = "example-fast"
base_url = "https://example.invalid/groq/v1"
api_key_env = "GROQ_API_KEY"
usd_per_call = 0

[providers.gemini]
model = "example-fast"
base_url = "https://example.invalid/gemini/v1"
api_key_env = "GEMINI_API_KEY"
usd_per_call = 0

[providers.batch]
model = "example-batch"
base_url = "https://example.invalid/batch/v1"
api_key_env = "MACH_BATCH_API_KEY"
usd_per_call = 0.04

[providers.deepinfra]
model = "example-cheap"
base_url = "https://example.invalid/cheap/v1"
api_key_env = "DEEPINFRA_API_KEY"
usd_per_call = 0.05

[providers.frontier]
model = "example-strong"
base_url = "https://example.invalid/strong/v1"
api_key_env = "MACH_FRONTIER_API_KEY"
usd_per_call = 0.05

[classes]
triage = ["local", "free", "batch", "cheap", "strong"]
extraction = ["local", "free", "batch", "cheap", "strong"]
synthesis = ["local", "free", "batch", "cheap", "strong"]
reasoning = ["local", "free", "batch", "cheap", "strong"]
chat = ["local", "free", "batch", "cheap", "strong"]
code = ["local", "free", "batch", "cheap", "strong"]

[channels.imessage]
policy = "sticky-with-escalation"
start_tier = "free"

[channels.cli]
policy = "unrestricted"

[budgets]
default_max_usd_per_day = 0

[budgets.subsystems]
demo = 1.0
"""


class Script(object):
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = []

    def __call__(self, provider, model, prompt):
        self.calls.append((provider["id"], model, prompt))
        code = self.codes.pop(0)
        if code == 200:
            return {"status": 200, "text": "ok"}
        return {"status": code, "text": "err"}


class Clock(object):
    def __init__(self, dt):
        self.dt = dt

    def __call__(self):
        return self.dt


class RouterTest(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in KEY_NAMES}
        for name in KEY_NAMES:
            os.environ[name] = KEY
        self.cfg = normalize(loads(BASE))
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(self.tmp.name, now=Clock(datetime.datetime(2026, 10, 9, 12, 0, 0)))

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.tmp.cleanup()

    def request(self, **kwargs):
        req = {"task_class": "triage", "channel": "cli", "subsystem": "demo", "urgent": True, "prompt": "hello"}
        req.update(kwargs)
        return req

    def test_parser_matches_tomllib(self):
        with open(os.path.join(ROOT, "models.toml"), "r", encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(loads(committed), tomllib.loads(committed))
        self.assertEqual(loads(BASE), tomllib.loads(BASE))

    def test_committed_config_routes_by_task_class_and_channel(self):
        cfg = load_config(os.path.join(ROOT, "models.toml"))
        self.assertEqual(list(cfg["classes"]), ["triage", "extraction", "synthesis", "reasoning", "chat", "code"])
        self.assertEqual(cfg["ladder"], ["local", "free", "batch", "cheap", "strong"])
        self.assertEqual(cfg["tiers"]["batch"]["discount"], 0.5)
        self.assertFalse(cfg["tiers"]["local"]["billable"])
        self.assertFalse(cfg["tiers"]["free"]["billable"])
        self.assertEqual(cfg["channels"]["imessage"]["policy"], "sticky-with-escalation")
        self.assertEqual(cfg["channels"]["cli"]["policy"], "unrestricted")
        cli = plan(cfg, self.request(task_class="code"), self.state, check_keys=False)
        chat = plan(cfg, self.request(task_class="chat", channel="imessage", conversation_id="c1"), self.state, check_keys=False)
        self.assertEqual(cli["task_class"], "code")
        self.assertEqual(chat["task_class"], "chat")
        self.assertEqual([item["provider"] for item in cli["candidates"][:5]], ["ollama", "groq", "gemini", "openrouter", "cerebras"])
        self.assertEqual([item["provider"] for item in chat["candidates"]], ["groq", "gemini", "openrouter", "cerebras"])
        skipped = {item["provider"]: item["reason"] for item in chat["skipped"]}
        self.assertEqual(skipped["ollama"], "channel-start")
        self.assertEqual(skipped["batch"], "not-urgent")
        self.assertEqual(skipped["deepinfra"], "budget")
        self.assertEqual(skipped["frontier"], "unconfigured")

    def test_task_class_selects_its_own_ladder(self):
        self.cfg["classes"]["triage"] = ["free"]
        self.cfg["classes"]["code"] = ["cheap", "strong"]
        triage = invoke(self.cfg, self.request(task_class="triage"), self.state, Script([200]))
        code = invoke(self.cfg, self.request(task_class="code"), self.state, Script([200]))
        self.assertEqual(triage["provider"], "groq")
        self.assertEqual(triage["tier"], "free")
        self.assertEqual(triage["model"], "example-fast")
        self.assertEqual(code["provider"], "deepinfra")
        self.assertEqual(code["tier"], "cheap")
        self.assertEqual(code["model"], "example-cheap")

    def test_fallback_rotates_on_auth_quota_and_server_errors(self):
        self.cfg["classes"]["triage"] = ["free"]
        for status in (429, 401, 402, 500, 503):
            script = Script([status, 200])
            result = invoke(self.cfg, self.request(), self.state, script)
            self.assertEqual(script.calls[0][0], "groq", status)
            self.assertEqual(script.calls[1][0], "gemini", status)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["provider"], "gemini")
            self.assertEqual([item["status"] for item in result["attempts"]], [status])

    def test_within_tier_success_is_not_an_escalation(self):
        self.cfg["classes"]["chat"] = ["free", "cheap"]
        script = Script([429, 200])
        result = invoke(self.cfg, self.request(task_class="chat", channel="imessage", conversation_id="c1"), self.state, script)
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["notice"], "")

    def test_imessage_starts_fast_escalates_and_sticks(self):
        script = Script([503, 503, 200])
        first = invoke(self.cfg, self.request(channel="imessage", conversation_id="c1"), self.state, script)
        self.assertEqual([call[0] for call in script.calls], ["groq", "gemini", "deepinfra"])
        self.assertEqual(first["notice"], "escalated from free to cheap")
        self.assertNotIn("ollama", [call[0] for call in script.calls])
        second = invoke(self.cfg, self.request(channel="imessage", conversation_id="c1"), self.state, Script([200]))
        self.assertEqual(second["provider"], "deepinfra")
        self.assertEqual(second["notice"], "")
        other = invoke(self.cfg, self.request(channel="imessage", conversation_id="c2"), self.state, Script([200]))
        self.assertEqual(other["provider"], "groq")

    def test_cli_is_unrestricted_and_may_start_local(self):
        script = Script([200])
        result = invoke(self.cfg, self.request(channel="cli"), self.state, script)
        self.assertEqual(script.calls[0][0], "ollama")
        self.assertEqual(result["tier"], "local")
        self.assertEqual(result["notice"], "")

    def test_budget_blocks_paid_tiers_and_ignores_free(self):
        self.cfg["budgets"]["subsystems"]["demo"] = 0.05
        self.cfg["classes"]["extraction"] = ["free", "cheap", "strong"]
        first = invoke(self.cfg, self.request(task_class="extraction"), self.state, Script([429, 429, 200]))
        self.assertEqual(first["provider"], "deepinfra")
        self.assertEqual(self._spent(), 0.05)
        second_script = Script([200])
        second = invoke(self.cfg, self.request(task_class="extraction"), self.state, second_script)
        self.assertEqual(second["provider"], "groq")
        self.assertEqual(second_script.calls[0][0], "groq")
        self.assertEqual(self._spent(), 0.05)
        planned = plan(self.cfg, self.request(task_class="extraction"), self.state)
        reasons = {item["provider"]: item["reason"] for item in planned["skipped"]}
        self.assertEqual(reasons["deepinfra"], "budget")
        self.assertEqual(reasons["frontier"], "budget")

    def test_batch_is_half_price_and_not_for_urgent_work(self):
        self.cfg["classes"]["synthesis"] = ["batch"]
        urgent = invoke(self.cfg, self.request(task_class="synthesis", urgent=True), self.state, Script([200]))
        self.assertEqual(urgent["status"], "degraded")
        self.assertEqual(urgent["message"], STRONG_UNAVAILABLE)
        self.assertFalse(os.path.exists(self.state.spend_path))
        queued_clock = self.state
        result = invoke(self.cfg, self.request(task_class="synthesis", urgent=False), queued_clock, Script([200]))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "batch")
        self.assertEqual(self._spent(), 0.02)

    def test_spend_resets_the_next_day_and_is_per_subsystem(self):
        self.cfg["budgets"]["subsystems"]["demo"] = 0.05
        self.cfg["budgets"]["subsystems"]["other"] = 0.05
        self.cfg["classes"]["triage"] = ["cheap"]
        invoke(self.cfg, self.request(), self.state, Script([200]))
        other = invoke(self.cfg, self.request(subsystem="other"), self.state, Script([200]))
        self.assertEqual(other["status"], "ok")
        blocked = invoke(self.cfg, self.request(), self.state, Script([200]))
        self.assertEqual(blocked["status"], "degraded")
        self.state.now.dt = datetime.datetime(2026, 10, 10, 12, 0, 0)
        again = invoke(self.cfg, self.request(), self.state, Script([200]))
        self.assertEqual(again["status"], "ok")
        self.assertEqual(self._spent(), 0.05)

    def test_interactive_failure_is_honest_and_non_urgent_is_queued(self):
        self.cfg["classes"]["reasoning"] = ["strong"]
        interactive = invoke(self.cfg, self.request(task_class="reasoning", prompt=PROMPT), self.state, Script([500]))
        self.assertEqual(interactive["status"], "degraded")
        self.assertEqual(interactive["message"], "strong model unavailable")
        self.assertFalse(os.path.exists(self.state.queue_path))
        queued = invoke(self.cfg, self.request(task_class="reasoning", urgent=False, prompt=PROMPT), self.state, Script([500]))
        self.assertEqual(queued["status"], "queued")
        self.assertTrue(queued["queue_id"].startswith("q-"))
        with open(self.state.queue_path, "r", encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("reasoning", body)
        self.assertNotIn(PROMPT, body)
        self.assertNotIn(KEY, body)
        self.assertNotIn(PROMPT, self._state_text())

    def test_missing_key_rotates_without_calling_or_recording_the_key(self):
        os.environ.pop("GROQ_API_KEY")
        self.cfg["classes"]["triage"] = ["free"]
        script = Script([200])
        result = invoke(self.cfg, self.request(prompt=PROMPT), self.state, script)
        self.assertEqual(script.calls[0][0], "gemini")
        self.assertEqual(result["attempts"][0], {"provider": "groq", "model": "example-fast", "tier": "free", "status": 401})
        dumped = self._state_text()
        self.assertNotIn(KEY, dumped)
        self.assertNotIn(PROMPT, dumped)

    def test_rejected_playwright_path_and_credential_urls(self):
        raw = loads(BASE)
        raw["providers"]["ollama"]["transport"] = "playwright"
        with self.assertRaises(ConfigError):
            normalize(raw)
        text = BASE.replace('providers = ["ollama"]', 'providers = ["playwright"]').replace("[providers.ollama]", "[providers.playwright]")
        with self.assertRaises(ConfigError):
            normalize(loads(text))
        raw = loads(BASE)
        raw["providers"]["groq"]["base_url"] = "https://user:secret@example.invalid/v1"
        with self.assertRaises(ConfigError):
            normalize(raw)
        with self.assertRaises(ConfigError):
            plan(self.cfg, self.request(task_class="poetry"), self.state)

    def test_python_sources_do_not_name_a_model(self):
        banned = ("example-fast", "example-local", "example-cheap", "example-batch", "example-strong", "claude-", "gemini-")
        package = os.path.join(ROOT, "model_router")
        for name in os.listdir(package):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(package, name), "r", encoding="utf-8") as fh:
                text = fh.read()
            for token in banned:
                self.assertNotIn(token, text, name)

    def test_cli_dry_run_is_task_class_json_and_writes_nothing(self):
        state_dir = os.path.join(self.tmp.name, "empty")
        env = os.environ.copy()
        for name in KEY_NAMES:
            env.pop(name, None)
        env["PYTHONPATH"] = ROOT
        proc = subprocess.run(
            [sys.executable, "-m", "model_router", "--class", "triage", "--channel", "cli",
             "--subsystem", "demo", "--dry-run", "--json", "--root", ROOT, "--state-dir", state_dir],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["task_class"], "triage")
        self.assertEqual(data["candidates"][0]["provider"], "ollama")
        reasons = {item["provider"]: item["reason"] for item in data["skipped"]}
        self.assertEqual(reasons["groq"], "missing GROQ_API_KEY")
        self.assertFalse(os.path.exists(state_dir))
        bad = subprocess.run(
            [sys.executable, "-m", "model_router", "--class", "poetry", "--subsystem", "demo", "--dry-run", "--root", ROOT],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 2)

    def test_transport_keeps_the_key_out_of_the_result(self):
        seen = {}

        class Resp(object):
            status = 200

            def read(self):
                return b'{"choices":[{"message":{"content":"hello"}}]}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def opener(req, timeout=60):
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = req.data.decode("utf-8")
            return Resp()

        result = post_chat(
            {"base_url": "https://example.invalid/v1", "api_key_env": "GROQ_API_KEY"},
            "from-config", "hi", opener=opener)
        self.assertEqual(result, {"status": 200, "text": "hello"})
        self.assertIn(KEY, seen["auth"])
        self.assertIn("from-config", seen["body"])
        self.assertNotIn(KEY, json.dumps(result))

        def denied(req, timeout=60):
            raise urllib.error.HTTPError(req.full_url, 429, "rate", hdrs=None, fp=None)

        self.assertEqual(post_chat({"base_url": "https://example.invalid/v1", "api_key_env": "GROQ_API_KEY"}, "m", "hi", opener=denied)["status"], 429)

    def _spent(self):
        with open(self.state.spend_path, "r", encoding="utf-8") as fh:
            return json.load(fh)["spent"]["demo"]

    def _state_text(self):
        chunks = []
        for name in os.listdir(self.tmp.name):
            path = os.path.join(self.tmp.name, name)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    chunks.append(fh.read())
        return "\n".join(chunks)


if __name__ == "__main__":
    unittest.main()
