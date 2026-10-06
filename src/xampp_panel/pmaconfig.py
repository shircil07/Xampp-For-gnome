"""Text edits for phpMyAdmin's config.inc.php.

The file is parsed as text and never executed. Only one-line assignments of
single-quoted strings are read or written, e.g.
    $cfg['Servers'][$i]['controlpass'] = 'secret';
"""

import re

KEYS = ("auth_type", "controluser", "controlpass", "pmadb")
_ASSIGN = r"""(?m)^([ \t]*\$cfg\['Servers'\]\[\$i\]\['KEY'\][ \t]*=[ \t]*)'((?:[^'\\\n]|\\.)*)'([ \t]*;.*)$"""
_SERVER_LINE = re.compile(r"(?m)^[ \t]*\$cfg\['Servers'\]\[\$i\]\[.*$")
_PHP_ESCAPE = re.compile(r"\\([\\'])")


def _pattern(key: str) -> re.Pattern:
    if key not in KEYS:
        raise ValueError(f"unsupported phpMyAdmin setting: {key}")
    return re.compile(_ASSIGN.replace("KEY", key))


def get_value(text: str, key: str) -> str | None:
    """Value of the last active assignment of `key` (commented-out lines are ignored), or None."""
    matches = list(_pattern(key).finditer(text))
    return _PHP_ESCAPE.sub(r"\1", matches[-1][2]) if matches else None


def set_value(text: str, key: str, value: str) -> str:
    """Rewrite the last active assignment of `key`, or add one after the last server setting."""
    if any(c in value for c in "\n\r\0"):
        raise ValueError("phpMyAdmin settings cannot contain line breaks or NUL")
    literal = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    matches = list(_pattern(key).finditer(text))
    if matches:
        m = matches[-1]
        return text[:m.start()] + m[1] + literal + m[3] + text[m.end():]
    line = f"$cfg['Servers'][$i]['{key}'] = {literal};"
    servers = list(_SERVER_LINE.finditer(text))
    if servers:
        end = servers[-1].end()
        return text[:end] + "\n" + line + text[end:]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"
