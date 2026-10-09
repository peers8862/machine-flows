"""Route a completion by task class, then fall back and account for spend.

The router proposal was not available. This follows that proposal:
ordered tiers, per-class ladders, rotation on 401/402/429/5xx, a daily USD cap
per subsystem (local and free exempt, batch at half price), iMessage sticky
escalation, and an unrestricted CLI. Interactive failure says the strong model
is unavailable. Non-urgent failure is queued. Headless Playwright to ChatGPT
is rejected at load.
"""

import datetime
import json
import os
import uuid

from model_router.tomlutil import TomlError, loads

TASK_CLASSES = ("triage", "extraction", "synthesis", "reasoning", "chat", "code")
TIER_ORDER = ("local", "free", "batch", "cheap", "strong")
STRONG_UNAVAILABLE = "strong model unavailable"
REJECTED_IDS = frozenset(("chatgpt-web", "playwright", "playwright-chatgpt", "headless-playwright"))
REJECTED_TRANSPORTS = frozenset(("playwright", "chatgpt-web", "headless-playwright"))

_TIER_KEYS = frozenset(("billable", "fast", "non_urgent_only", "discount", "providers"))
_PROVIDER_KEYS = frozenset(("model", "base_url", "api_key_env", "usd_per_call", "transport"))


class ConfigError(ValueError):
    pass


class State(object):
    def __init__(self, directory, now=None):
        self.directory = directory
        self.now = now or datetime.datetime.now

    @property
    def spend_path(self):
        return os.path.join(self.directory, "spend.json")

    @property
    def sticky_path(self):
        return os.path.join(self.directory, "sticky.json")

    @property
    def queue_path(self):
        return os.path.join(self.directory, "queue.jsonl")


def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = loads(fh.read())
    except TomlError as err:
        raise ConfigError(str(err))
    except OSError:
        raise ConfigError("cannot read %s" % path)
    return normalize(raw)


def normalize(raw):
    if not isinstance(raw, dict):
        raise ConfigError("config must be a table")
    extra = set(raw) - {"schema", "ladder", "tiers", "providers", "classes", "channels", "budgets"}
    if extra:
        raise ConfigError("unknown keys: %s" % ", ".join(sorted(extra)))
    if raw.get("schema") != 1:
        raise ConfigError("schema must be 1")
    ladder = raw.get("ladder") or {}
    _only(ladder, ("order",), "ladder")
    if list(ladder.get("order") or []) != list(TIER_ORDER):
        raise ConfigError("ladder.order must be local, free, batch, cheap, strong")
    tiers_raw = raw.get("tiers") or {}
    providers_raw = raw.get("providers") or {}
    if set(tiers_raw) != set(TIER_ORDER):
        raise ConfigError("tiers must be exactly local, free, batch, cheap, strong")
    tiers = {}
    providers = {}
    for name in TIER_ORDER:
        src = tiers_raw[name]
        if not isinstance(src, dict):
            raise ConfigError("tier %s must be a table" % name)
        _only(src, _TIER_KEYS, "tier %s" % name)
        billable = _bool(src.get("billable"), "tier %s billable" % name)
        fast = _bool(src.get("fast"), "tier %s fast" % name)
        non_urgent_only = _bool(src.get("non_urgent_only", False), "tier %s non_urgent_only" % name)
        if name in ("local", "free"):
            if billable:
                raise ConfigError("%s is exempt from budgets" % name)
        elif not billable:
            raise ConfigError("%s is a paid tier" % name)
        if name == "free":
            if not fast:
                raise ConfigError("free is the fast tier")
        elif fast:
            raise ConfigError("only free is marked fast")
        if name == "batch":
            if not non_urgent_only:
                raise ConfigError("batch is non-urgent only")
            if float(src.get("discount", -1)) != 0.5:
                raise ConfigError("batch discount must be 0.5")
            discount = 0.5
        else:
            if non_urgent_only:
                raise ConfigError("%s is not a non-urgent tier" % name)
            if "discount" in src:
                raise ConfigError("%s does not take a discount" % name)
            discount = 1.0
        ids = src.get("providers")
        if not isinstance(ids, list) or not ids or not all(isinstance(item, str) and item for item in ids):
            raise ConfigError("tier %s needs providers" % name)
        for pid in ids:
            if pid in REJECTED_IDS:
                raise ConfigError("provider %s is rejected: headless Playwright to ChatGPT is not a provider" % pid)
            if pid in providers:
                raise ConfigError("provider %s is listed on more than one tier" % pid)
            body = providers_raw.get(pid)
            if not isinstance(body, dict):
                raise ConfigError("missing [providers.%s]" % pid)
            providers[pid] = _provider(pid, name, body, billable)
        tiers[name] = {
            "billable": billable,
            "fast": fast,
            "non_urgent_only": non_urgent_only,
            "discount": discount,
            "providers": list(ids),
        }
    extra_providers = set(providers_raw) - set(providers)
    if extra_providers:
        raise ConfigError("unassigned providers: %s" % ", ".join(sorted(extra_providers)))
    return {
        "schema": 1,
        "ladder": list(TIER_ORDER),
        "tiers": tiers,
        "providers": providers,
        "classes": _classes(raw.get("classes") or {}),
        "channels": _channels(raw.get("channels") or {}, tiers),
        "budgets": _budgets(raw.get("budgets") or {}),
    }


def plan(config, request, state=None, check_keys=False):
    """Choose the ordered candidates for this call. Does not contact a provider."""
    req = _request(request)
    skipped = []
    ladder = list(config["classes"][req["task_class"]])
    floor = ""
    if req["channel"] == "imessage":
        floor = config["channels"]["imessage"]["start_tier"]
        sticky = _sticky_get(state, req["conversation_id"])
        reason = "channel-start"
        if sticky:
            floor = sticky
            reason = "sticky"
        ladder, dropped = _drop_before(config, ladder, floor, reason)
        skipped.extend(dropped)
    candidates = []
    for tier_name in ladder:
        tier = config["tiers"][tier_name]
        if tier["non_urgent_only"] and req["urgent"]:
            for pid in tier["providers"]:
                skipped.append(_skip(pid, tier_name, "not-urgent"))
            continue
        for pid in tier["providers"]:
            provider = config["providers"][pid]
            reason = _availability(provider, tier, req, state, config, check_keys)
            if reason:
                skipped.append(_skip(pid, tier_name, reason))
                continue
            candidates.append({
                "provider": pid,
                "model": provider["model"],
                "tier": tier_name,
                "billable": tier["billable"],
                "usd": _charge_of(provider, tier),
            })
    return {
        "status": "plan",
        "task_class": req["task_class"],
        "channel": req["channel"],
        "subsystem": req["subsystem"],
        "urgent": req["urgent"],
        "floor": floor,
        "candidates": candidates,
        "skipped": skipped,
    }


def invoke(config, request, state, complete):
    """Walk the plan. 401, 402, 429, and 5xx rotate to the next provider; so does any other non-2xx."""
    if state is None:
        raise ConfigError("invoke needs a state directory so spend and the queue are recorded")
    req = _request(request)
    planned = plan(config, req, state, check_keys=False)
    attempts = []
    for cand in planned["candidates"]:
        provider = config["providers"][cand["provider"]]
        env_name = provider["api_key_env"]
        if env_name and not os.environ.get(env_name):
            attempts.append(_attempt(cand, 401))
            continue
        result = complete(_view(cand, provider), cand["model"], req["prompt"])
        if not isinstance(result, dict) or "status" not in result:
            raise ConfigError("transport returned no status")
        status = int(result["status"])
        if 200 <= status < 300:
            if cand["billable"]:
                _charge(state, req["subsystem"], cand["usd"])
            if req["channel"] == "imessage" and req["conversation_id"]:
                _sticky_set(state, req["conversation_id"], cand["tier"])
            notice = _notice(config, req, planned["floor"], cand["tier"])
            return _done(req, cand, attempts, planned["skipped"], result.get("text") or "", notice)
        attempts.append(_attempt(cand, status))
    return _give_up(req, state, attempts, planned["skipped"])


def _provider(pid, tier_name, body, billable):
    _only(body, _PROVIDER_KEYS, "provider %s" % pid)
    transport = body.get("transport") or "openai"
    if transport in REJECTED_TRANSPORTS:
        raise ConfigError("provider %s transport is rejected: headless Playwright to ChatGPT is not a transport" % pid)
    if transport != "openai":
        raise ConfigError("provider %s transport must be openai" % pid)
    model = body.get("model", "")
    base_url = body.get("base_url", "")
    if not isinstance(model, str) or not isinstance(base_url, str):
        raise ConfigError("provider %s model and base_url must be strings" % pid)
    if base_url:
        _check_url(pid, base_url)
    env_name = body.get("api_key_env", "")
    if not isinstance(env_name, str):
        raise ConfigError("provider %s api_key_env must be a string" % pid)
    if tier_name == "local":
        if env_name:
            raise ConfigError("local provider %s must not name an api key" % pid)
    elif not _env_name(env_name):
        raise ConfigError("provider %s needs an api_key_env name" % pid)
    usd = body.get("usd_per_call", 0)
    if isinstance(usd, bool) or not isinstance(usd, (int, float)):
        raise ConfigError("provider %s usd_per_call must be a number" % pid)
    usd = float(usd)
    if billable and usd <= 0:
        raise ConfigError("provider %s needs usd_per_call > 0" % pid)
    if not billable and usd != 0:
        raise ConfigError("provider %s is exempt and must cost 0" % pid)
    return {"model": model, "base_url": base_url, "api_key_env": env_name, "usd_per_call": usd}


def _classes(raw):
    if set(raw) != set(TASK_CLASSES):
        missing = [name for name in TASK_CLASSES if name not in raw]
        extra = [name for name in raw if name not in TASK_CLASSES]
        raise ConfigError("classes must be %s (missing %s, extra %s)" % (
            ", ".join(TASK_CLASSES), ", ".join(missing) or "-", ", ".join(extra) or "-"))
    out = {}
    for name in TASK_CLASSES:
        tiers = raw[name]
        if not isinstance(tiers, list) or not tiers or not all(isinstance(item, str) for item in tiers):
            raise ConfigError("class %s needs a tier list" % name)
        if not _is_subsequence(tiers, TIER_ORDER):
            raise ConfigError("class %s must follow ladder order" % name)
        out[name] = list(tiers)
    return out


def _channels(raw, tiers):
    if set(raw) != {"imessage", "cli"}:
        raise ConfigError("channels must be imessage and cli")
    imessage = raw["imessage"]
    cli = raw["cli"]
    if not isinstance(imessage, dict) or not isinstance(cli, dict):
        raise ConfigError("channels must be tables")
    _only(imessage, ("policy", "start_tier"), "channels.imessage")
    _only(cli, ("policy",), "channels.cli")
    if imessage.get("policy") != "sticky-with-escalation":
        raise ConfigError("imessage policy must be sticky-with-escalation")
    if cli.get("policy") != "unrestricted":
        raise ConfigError("cli policy must be unrestricted")
    start = imessage.get("start_tier")
    if start not in tiers or not tiers[start]["fast"]:
        raise ConfigError("imessage start_tier must be the fast tier")
    return {
        "imessage": {"policy": "sticky-with-escalation", "start_tier": start},
        "cli": {"policy": "unrestricted"},
    }


def _budgets(raw):
    if not isinstance(raw, dict):
        raise ConfigError("budgets must be a table")
    _only(raw, ("default_max_usd_per_day", "subsystems"), "budgets")
    default = raw.get("default_max_usd_per_day", 0)
    default = _usd(default, "default_max_usd_per_day")
    subs = raw.get("subsystems") or {}
    if not isinstance(subs, dict):
        raise ConfigError("budgets.subsystems must be a table")
    clean = {}
    for key, val in subs.items():
        clean[str(key)] = _usd(val, "budget for %s" % key)
    return {"default_max_usd_per_day": default, "subsystems": clean}


def _request(raw):
    if not isinstance(raw, dict):
        raise ConfigError("request must be a dict")
    task = raw.get("task_class", raw.get("class"))
    if task not in TASK_CLASSES:
        raise ConfigError("unknown task class %r" % (task,))
    channel = raw.get("channel") or "cli"
    if channel not in ("cli", "imessage"):
        raise ConfigError("unknown channel %r" % (channel,))
    subsystem = raw.get("subsystem")
    if not isinstance(subsystem, str) or not subsystem.strip():
        raise ConfigError("subsystem is required")
    urgent = raw.get("urgent", True)
    if not isinstance(urgent, bool):
        raise ConfigError("urgent must be a bool")
    if channel == "imessage":
        urgent = True
    conversation = raw.get("conversation_id") or ""
    if not isinstance(conversation, str):
        raise ConfigError("conversation_id must be a string")
    prompt = raw.get("prompt") or ""
    if not isinstance(prompt, str):
        raise ConfigError("prompt must be a string")
    return {
        "task_class": task,
        "channel": channel,
        "subsystem": subsystem.strip(),
        "urgent": urgent,
        "conversation_id": conversation,
        "prompt": prompt,
    }


def _availability(provider, tier, req, state, config, check_keys):
    if not provider["model"] or not provider["base_url"]:
        return "unconfigured"
    if tier["billable"] and provider["usd_per_call"] <= 0:
        return "unpriced"
    if check_keys and provider["api_key_env"] and not os.environ.get(provider["api_key_env"]):
        return "missing " + provider["api_key_env"]
    if tier["billable"]:
        cost = _charge_of(provider, tier)
        cap = _cap(config, req["subsystem"])
        if _money(_spent(state, req["subsystem"]) + cost) > cap:
            return "budget"
    return ""


def _drop_before(config, ladder, floor, reason):
    floor_i = config["ladder"].index(floor)
    keep = []
    skipped = []
    for tier_name in ladder:
        if config["ladder"].index(tier_name) < floor_i:
            for pid in config["tiers"][tier_name]["providers"]:
                skipped.append(_skip(pid, tier_name, reason))
        else:
            keep.append(tier_name)
    return keep, skipped


def _notice(config, req, floor, tier_name):
    if req["channel"] != "imessage" or not floor:
        return ""
    if config["ladder"].index(tier_name) <= config["ladder"].index(floor):
        return ""
    return "escalated from %s to %s" % (floor, tier_name)


def _give_up(req, state, attempts, skipped):
    base = {
        "task_class": req["task_class"],
        "channel": req["channel"],
        "subsystem": req["subsystem"],
        "provider": "",
        "model": "",
        "tier": "",
        "text": "",
        "notice": "",
        "attempts": attempts,
        "skipped": skipped,
        "queue_id": "",
    }
    if req["urgent"]:
        base["status"] = "degraded"
        base["message"] = STRONG_UNAVAILABLE
        return base
    queue_id = _enqueue(state, req, attempts)
    base["status"] = "queued"
    base["message"] = "queued"
    base["queue_id"] = queue_id
    return base


def _done(req, cand, attempts, skipped, text, notice):
    return {
        "status": "ok",
        "task_class": req["task_class"],
        "channel": req["channel"],
        "subsystem": req["subsystem"],
        "provider": cand["provider"],
        "model": cand["model"],
        "tier": cand["tier"],
        "text": text,
        "message": "",
        "notice": notice,
        "attempts": attempts,
        "skipped": skipped,
        "queue_id": "",
    }


def _view(cand, provider):
    return {
        "id": cand["provider"],
        "base_url": provider["base_url"],
        "api_key_env": provider["api_key_env"],
    }


def _attempt(cand, status):
    return {"provider": cand["provider"], "model": cand["model"], "tier": cand["tier"], "status": status}


def _skip(pid, tier_name, reason):
    return {"provider": pid, "tier": tier_name, "reason": reason}


def _charge_of(provider, tier):
    return _money(provider["usd_per_call"] * tier["discount"])


def _cap(config, subsystem):
    budgets = config["budgets"]
    if subsystem in budgets["subsystems"]:
        return budgets["subsystems"][subsystem]
    return budgets["default_max_usd_per_day"]


def _spent(state, subsystem):
    if state is None:
        return 0.0
    data = _load_spend(state)
    return _money(data["spent"].get(subsystem, 0.0))


def _charge(state, subsystem, usd):
    data = _load_spend(state)
    data["spent"][subsystem] = _money(data["spent"].get(subsystem, 0.0) + usd)
    _write_json(state.spend_path, data)


def _load_spend(state):
    today = state.now().strftime("%Y-%m-%d")
    data = _read_json(state.spend_path)
    if not data or data.get("date") != today or not isinstance(data.get("spent"), dict):
        return {"date": today, "spent": {}}
    return data


def _sticky_get(state, conversation_id):
    if state is None or not conversation_id:
        return ""
    data = _read_json(state.sticky_path)
    conversations = data.get("conversations") if isinstance(data, dict) else None
    if not isinstance(conversations, dict):
        return ""
    tier = conversations.get(conversation_id) or ""
    if tier not in TIER_ORDER:
        return ""
    return tier


def _sticky_set(state, conversation_id, tier_name):
    data = _read_json(state.sticky_path)
    if not isinstance(data, dict) or not isinstance(data.get("conversations"), dict):
        data = {"conversations": {}}
    data["conversations"][conversation_id] = tier_name
    _write_json(state.sticky_path, data)


def _enqueue(state, req, attempts):
    os.makedirs(state.directory, exist_ok=True)
    queue_id = "q-" + uuid.uuid4().hex[:8]
    record = {
        "id": queue_id,
        "task_class": req["task_class"],
        "channel": req["channel"],
        "subsystem": req["subsystem"],
        "conversation_id": req["conversation_id"],
        "queued_at": state.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "reason": "no provider accepted",
        "attempts": attempts,
    }
    with open(state.queue_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return queue_id


def _read_json(path):
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _only(src, allowed, label):
    extra = set(src) - set(allowed)
    if extra:
        raise ConfigError("%s has unknown keys: %s" % (label, ", ".join(sorted(extra))))


def _bool(value, label):
    if not isinstance(value, bool):
        raise ConfigError("%s must be a bool" % label)
    return value


def _usd(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise ConfigError("%s must be >= 0" % label)
    return _money(value)


def _money(value):
    return round(float(value), 6)


def _env_name(value):
    if not value:
        return False
    first = value[0]
    if not ("A" <= first <= "Z"):
        return False
    for char in value[1:]:
        if not (("A" <= char <= "Z") or ("0" <= char <= "9") or char == "_"):
            return False
    return True


def _check_url(pid, url):
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ConfigError("provider %s base_url must be http(s)" % pid)
    lowered = url.lower()
    if "@" in url or "api_key=" in lowered or "token=" in lowered:
        raise ConfigError("provider %s base_url must not carry credentials" % pid)


def _is_subsequence(part, whole):
    last = -1
    whole = list(whole)
    for item in part:
        if item not in whole:
            return False
        pos = whole.index(item)
        if pos <= last:
            return False
        last = pos
    return True
