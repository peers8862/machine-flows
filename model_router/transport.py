"""OpenAI-compatible chat call. The API key stays in the process environment."""

import json
import os
import urllib.error
import urllib.request


def post_chat(provider, model, prompt, opener=None, timeout=60):
    """Return {status, text}. The key is never copied into the result."""
    env_name = provider.get("api_key_env") or ""
    key = ""
    if env_name:
        key = os.environ.get(env_name) or ""
        if not key:
            return {"status": 401, "text": ""}
    base = (provider.get("base_url") or "").rstrip("/")
    if not base:
        return {"status": 503, "text": ""}
    url = base + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
    except urllib.error.HTTPError as err:
        return {"status": err.code, "text": ""}
    except urllib.error.URLError:
        return {"status": 503, "text": ""}
    if status < 200 or status >= 300:
        return {"status": status, "text": ""}
    try:
        body = json.loads(raw.decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError):
        return {"status": 502, "text": ""}
    if not isinstance(text, str):
        return {"status": 502, "text": ""}
    return {"status": status, "text": text}
