"""Focused checks for Windows app metadata and verified bundled CLI discovery."""

from pathlib import Path
import tempfile
from unittest.mock import patch

import runtime_discovery as D


def main():
    apps = D.inventory_apps([
        {"DisplayName": "OmniRoute", "DisplayVersion": "1.2", "Publisher": "Example",
         "InstallLocation": "C:/Apps/OmniRoute"},
        {"DisplayName": "Novel Editor", "InstallLocation": "C:/Apps/Novel"},
        {"DisplayName": "ZCode", "InstallLocation": "C:/Apps/ZCode"},
        {"DisplayName": "   "},
        None,
    ])
    assert next(app for app in apps if app["name"] == "OmniRoute")["cli"] == "omniroute"
    unknown = next(app for app in apps if app["name"] == "Novel Editor")
    assert unknown["cli"] is None and unknown["classification"] == "unclassified"
    assert unknown["candidate"] is True
    assert next(app for app in apps if app["name"] == "OmniRoute")["Publisher"] == "Example"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        script = root / "resources" / "glm" / "zcode.cjs"
        script.parent.mkdir(parents=True)
        script.write_text("// verified entry point\n", encoding="utf-8")
        zcode = [{"cli": "zcode", "location": str(root)}]
        with patch.object(D.shutil, "which", return_value="/mock/node"):
            assert D.bundled_cli(zcode, "zcode") == ["/mock/node", str(script)]
            assert D.bundled_cli(zcode, "other") is None
        with patch.object(D.shutil, "which", return_value=None):
            assert D.bundled_cli(zcode, "zcode") is None

        script.unlink()
        with patch.object(D.shutil, "which", return_value="/mock/node"):
            assert D.bundled_cli(zcode, "zcode") is None


if __name__ == "__main__":
    main()
