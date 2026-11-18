# SPDX-License-Identifier: AGPL-3.0-only
"""Validate an answer against its JSON Schema (data/schema/*.json).

Uses jsonschema when it is installed. Otherwise a small built-in check
covers the keywords these schemas use.
"""
import re

from . import seeds

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def _check(v, s, where, errs):
    if "anyOf" in s:
        if not any(not _check(v, sub, where, []) for sub in s["anyOf"]):
            errs.append(f"{where}: matches none of anyOf")
        return errs
    if "const" in s and v != s["const"]:
        errs.append(f"{where}: must be {s['const']!r}")
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{where}: {v!r} not in {s['enum']}")
    t = s.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_is(v, x) for x in ts):
            errs.append(f"{where}: type {type(v).__name__}, not {t}")
            return errs
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{where}: {v} < {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{where}: {v} > {s['maximum']}")
    if isinstance(v, str):
        if "minLength" in s and len(v) < s["minLength"]:
            errs.append(f"{where}: too short")
        if "maxLength" in s and len(v) > s["maxLength"]:
            errs.append(f"{where}: too long")
        if "pattern" in s and not re.search(s["pattern"], v):
            errs.append(f"{where}: does not match {s['pattern']}")
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            errs.append(f"{where}: fewer than {s['minItems']} items")
        if "maxItems" in s and len(v) > s["maxItems"]:
            errs.append(f"{where}: more than {s['maxItems']} items")
        if "items" in s:
            for i, x in enumerate(v):
                _check(x, s["items"], f"{where}[{i}]", errs)
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                errs.append(f"{where}: {k} is missing")
        props = s.get("properties", {})
        pats = s.get("patternProperties", {})
        for k, x in v.items():
            if k in props:
                _check(x, props[k], f"{where}.{k}", errs)
                continue
            hit = False
            for p, sub in pats.items():
                if re.search(p, k):
                    hit = True
                    _check(x, sub, f"{where}.{k}", errs)
            if not hit and s.get("additionalProperties") is False:
                errs.append(f"{where}: {k} is not allowed")
    return errs


def errors(obj, name):
    s = seeds.load("schema/" + name)
    try:
        import jsonschema

        v = jsonschema.Draft202012Validator(s)
        return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(obj)]
    except ImportError:
        return _check(obj, s, "$", [])


def errors_builtin(obj, name):
    return _check(obj, seeds.load("schema/" + name), "$", [])
