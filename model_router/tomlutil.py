"""TOML subset reader for models.toml (Python 3.9+).

Enough for this file: comments, dotted tables, strings, bools, numbers, and
one-line arrays. Not a general TOML library.
"""


class TomlError(ValueError):
    def __init__(self, msg, line=0):
        ValueError.__init__(self, "line %d: %s" % (line, msg) if line else msg)
        self.line = line


def loads(text):
    root = {}
    cur = root
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[["):
            raise TomlError("arrays of tables are not supported", lineno)
        if line.startswith("["):
            if not line.endswith("]"):
                raise TomlError("bad table header", lineno)
            cur = _enter(root, _split_dotted(line[1:-1].strip(), lineno), lineno)
            continue
        eq = _find_eq(line)
        if eq < 0:
            raise TomlError("expected key = value", lineno)
        key = line[:eq].strip()
        if not key or not all(c.isalnum() or c == "_" for c in key):
            raise TomlError("bad key %r" % key, lineno)
        if key in cur:
            raise TomlError("duplicate key %r" % key, lineno)
        cur[key] = _parse_value(line[eq + 1:].strip(), lineno)
    return root


def _enter(root, parts, lineno):
    cur = root
    for part in parts:
        nxt = cur.get(part)
        if nxt is None:
            nxt = {}
            cur[part] = nxt
        if not isinstance(nxt, dict):
            raise TomlError("key %r is not a table" % part, lineno)
        cur = nxt
    return cur


def _split_dotted(text, lineno):
    if not text:
        raise TomlError("empty table name", lineno)
    parts = text.split(".")
    for part in parts:
        if not part or not all(c.isalnum() or c == "_" for c in part):
            raise TomlError("bad table name %r" % text, lineno)
    return parts


def _strip_comment(s):
    out = []
    quote = False
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                quote = False
        elif c == '"':
            quote = True
            out.append(c)
        elif c == "#":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def _find_eq(line):
    quote = False
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < len(line):
                i += 2
                continue
            if c == '"':
                quote = False
            i += 1
            continue
        if c == '"':
            quote = True
        elif c == "=":
            return i
        i += 1
    return -1


def _parse_value(text, lineno):
    if text.startswith('"'):
        return _parse_string(text, lineno)
    if text.startswith("["):
        return _parse_array(text, lineno)
    if text == "true":
        return True
    if text == "false":
        return False
    token = text
    if any(c in token for c in ".eE"):
        try:
            return float(token)
        except ValueError:
            raise TomlError("cannot parse value %r" % text, lineno)
    try:
        return int(token)
    except ValueError:
        raise TomlError("cannot parse value %r" % text, lineno)


def _parse_string(text, lineno):
    if len(text) < 2 or not text.endswith('"'):
        # The closing quote must be the last character of the value.
        if not _closed_string(text):
            raise TomlError("unterminated string", lineno)
    chars = []
    i = 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            if i + 1 >= len(text):
                raise TomlError("unterminated string", lineno)
            esc = text[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
            if esc not in mapping:
                raise TomlError("bad escape", lineno)
            chars.append(mapping[esc])
            i += 2
            continue
        if c == '"':
            if i != len(text) - 1:
                raise TomlError("trailing characters after value", lineno)
            return "".join(chars)
        chars.append(c)
        i += 1
    raise TomlError("unterminated string", lineno)


def _closed_string(text):
    if not text.startswith('"'):
        return False
    i = 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return True
        i += 1
    return False


def _parse_array(text, lineno):
    if not text.endswith("]"):
        raise TomlError("unterminated array", lineno)
    body = text[1:-1].strip()
    if not body:
        return []
    parts = _split_array(body, lineno)
    return [_parse_value(part.strip(), lineno) for part in parts]


def _split_array(body, lineno):
    parts = []
    buf = []
    quote = False
    i = 0
    while i < len(body):
        c = body[i]
        if quote:
            buf.append(c)
            if c == "\\":
                if i + 1 >= len(body):
                    raise TomlError("unterminated string", lineno)
                buf.append(body[i + 1])
                i += 2
                continue
            if c == '"':
                quote = False
        elif c == '"':
            quote = True
            buf.append(c)
        elif c == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    if quote:
        raise TomlError("unterminated string", lineno)
    parts.append("".join(buf))
    return parts
