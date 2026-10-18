"""Windows application metadata helpers used by CLI agent discovery."""

import os
from pathlib import Path
import re
import shutil


APP_FAMILIES = (
    ("zcode", "Z.AI", r"\bzcode\b|\bz[.]ai\b"),
    ("claude", "Claude", r"\bclaude\b"),
    ("codex", "ChatGPT / Codex", r"\bchatgpt\b|\bcodex\b"),
    ("agy", "Antigravity", r"\bantigravity\b"),
    ("mcode", "MiniMax", r"\bminimax\b"),
    ("qwen", "Qwen", r"\bqwen\b"),
    ("deepseek", "DeepSeek", r"\bdeepseek\b"),
    ("kimi", "Kimi", r"\bkimi\b"),
    ("opencode", "OpenCode", r"\bopencode\b"),
    ("omniroute", "OmniRoute", r"\bomniroute\b"),
    ("lmstudio", "Local models", r"\blm studio\b"),
    ("ollama", "Local models", r"\bollama\b"),
)

APP_METADATA_FIELDS = ("DisplayName", "DisplayVersion", "Publisher", "InstallLocation")


def inventory_apps(rows):
    """Return named app metadata rows, retaining unknown apps as unclassified candidates."""
    found = {}
    for source in rows:
        if not isinstance(source, dict):
            continue
        name = source.get("DisplayName") or source.get("name")
        if not isinstance(name, str) or not name.strip() or re.search(r"[.-](bak|backup)(?:[.-]|$)", name, re.I):
            continue
        name = name.strip()
        family = next((item for item in APP_FAMILIES if re.search(item[2], name, re.I)), None)
        row = {field: source[field] for field in APP_METADATA_FIELDS
               if isinstance(source.get(field), (str, int))}
        row.update({"name": name, "cli": family[0] if family else None,
                    "subscription_group": family[1] if family else None,
                    "classification": "known" if family else "unclassified",
                    "candidate": True})
        row.setdefault("version", str(source.get("DisplayVersion") or "unknown"))
        row.setdefault("location", source.get("InstallLocation", ""))
        found[(name.casefold(), str(row.get("location", "")).casefold())] = row
    return sorted(found.values(), key=lambda row: (row["classification"] != "known",
                                                    row["subscription_group"] or "",
                                                    row["name"].casefold()))


def raw_windows_app_rows():
    """Collect raw uninstall registry and per-user Programs directory entries without launching apps."""
    if os.name != "nt":
        return []
    import winreg

    rows = []
    uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, uninstall, 0, winreg.KEY_READ | view) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as key:
                                row = {}
                                for field in APP_METADATA_FIELDS:
                                    try:
                                        value = winreg.QueryValueEx(key, field)[0]
                                        if isinstance(value, (str, int)):
                                            row[field] = value
                                    except OSError:
                                        pass
                                rows.append(row)
                        except OSError:
                            continue
            except OSError:
                continue
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) / "Programs" if local else None
    if base and base.is_dir():
        try:
            rows.extend({"DisplayName": child.name, "InstallLocation": str(child)}
                        for child in base.iterdir() if child.is_dir())
        except OSError:
            pass
    # Some uninstall entries omit InstallLocation; inspect only known installation roots.
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root and (Path(root) / "ZCode").is_dir():
            rows.append({"DisplayName": "ZCode", "InstallLocation": str(Path(root) / "ZCode")})
    return rows


def windows_app_metadata():
    """Read uninstall metadata and per-user Programs directory entries without launching apps."""
    return inventory_apps(raw_windows_app_rows())


def bundled_cli(apps, cli_id):
    """Return argv prefix for a verified bundled CLI, or None when it is unavailable."""
    if cli_id != "zcode":
        return None
    node = shutil.which("node")
    if not node:
        return None
    for app in apps:
        if not isinstance(app, dict) or app.get("cli") != cli_id:
            continue
        location = app.get("location") or app.get("InstallLocation")
        if not isinstance(location, str) or not location:
            continue
        script = Path(location) / "resources" / "glm" / "zcode.cjs"
        if script.is_file():
            return [node, str(script)]
    return None
