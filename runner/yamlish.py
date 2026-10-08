"""极简 YAML 子集解析器（仅够读 bench.yaml，避免引入第三方依赖）。

支持：缩进嵌套映射、块序列、行内 {a: b, c: d} 与 [a, b]、# 注释、单/双引号。
不支持：锚点、多行块标量、复杂转义。
"""
import re


def _scalar(s):
    s = s.strip()
    if not s:
        return None
    if s[0] in "\"'" and len(s) >= 2 and s[-1] == s[0]:
        return s[1:-1]
    if s.startswith("{") and s.endswith("}"):
        return _flow_map(s[1:-1])
    if s.startswith("[") and s.endswith("]"):
        return _flow_list(s[1:-1])
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_flow(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out if x.strip()]


def _flow_map(s):
    d = {}
    for item in _split_flow(s):
        if ":" in item:
            k, v = item.split(":", 1)
            d[k.strip().strip("\"'")] = _scalar(v)
    return d


def _flow_list(s):
    return [_scalar(x) for x in _split_flow(s)]


def _strip_comment(line):
    out, in_q = [], None
    for ch in line:
        if in_q:
            if ch == in_q:
                in_q = None
            out.append(ch)
        elif ch in "\"'":
            in_q = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def loads(text):
    lines = []
    for raw in text.splitlines():
        s = _strip_comment(raw)
        if not s.strip():
            continue
        indent = len(s) - len(s.lstrip(" "))
        lines.append((indent, s.strip()))
    if not lines:
        return {}
    val, _ = _parse_block(lines, 0, lines[0][0])
    return val


def _parse_block(lines, i, indent):
    """返回 (value, next_index)。按首行判断是映射还是序列。"""
    if lines[i][1].startswith("- "):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_seq(lines, i, indent):
    out = []
    while i < len(lines):
        ind, s = lines[i]
        if ind < indent or not s.startswith("- "):
            break
        item = s[2:].strip()
        child_start = i + 1
        if child_start < len(lines) and lines[child_start][0] > ind:
            v, i = _parse_block(lines, child_start, lines[child_start][0])
            if item and item.endswith(":"):
                out.append(v)
            else:
                out.append(item)
            continue
        out.append(_scalar(item))
        i += 1
    return out, i


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines):
        ind, s = lines[i]
        if ind < indent:
            break
        if ind > indent:
            i += 1
            continue
        if s.startswith("- "):
            break
        if ":" not in s:
            i += 1
            continue
        k, v = s.split(":", 1)
        k = k.strip().strip("\"'")
        v = v.strip()
        if v:
            out[k] = _scalar(v)
            i += 1
        else:
            if i + 1 < len(lines) and lines[i + 1][0] > ind:
                child, i2 = _parse_block(lines, i + 1, lines[i + 1][0])
                out[k] = child
                i = i2
            else:
                out[k] = None
                i += 1
    return out, i


def load(path):
    with open(path, encoding="utf-8") as f:
        return loads(f.read())
