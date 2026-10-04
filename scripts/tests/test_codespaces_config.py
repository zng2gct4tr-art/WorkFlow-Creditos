"""Config preparation uses temporary files and no provider accounts or payments."""

import importlib.util
from pathlib import Path
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "codespaces_start", ROOT / "scripts/codespaces_start.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_prepare_preserves_secrets_and_never_exports_into_git(tmp_path, capsys):
    shutil.copy2(ROOT / ".env.example", tmp_path / ".env.example")
    origin = module.prepare(tmp_path, "test-workflow-123", "app.github.dev")
    first = module.parse_settings(tmp_path / ".env")
    assert origin == "https://test-workflow-123-3000.app.github.dev"
    assert first["COOKIE_SECURE"] == "true" and first["WEB_SETUP_ENABLED"] == "true"
    assert len(first["WEB_SETUP_TOKEN"]) >= 32
    assert "replace-with" not in first["POSTGRES_PASSWORD"]
    module.prepare(tmp_path, "test-workflow-123", "app.github.dev")
    second = module.parse_settings(tmp_path / ".env")
    for key in [
        "POSTGRES_PASSWORD",
        "SESSION_SECRET",
        "AZURE_STORAGE_ACCOUNT_KEY",
        "STORAGE_ENCRYPTION_KEY",
        "WEB_SETUP_TOKEN",
    ]:
        assert first[key] == second[key]
        assert first[key] not in capsys.readouterr().out
    guide = (tmp_path / ".workflow/ABRIR-WEB.md").read_text()
    assert "/#setup=" in guide and "?setup=" not in guide
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    assert ".workflow/" in (ROOT / ".gitignore").read_text()


def test_rejects_untrusted_host_before_writing_secrets(tmp_path):
    with pytest.raises(RuntimeError, match="host"):
        module.prepare(tmp_path, "invalid/space", "app.github.dev")
    assert not (tmp_path / ".env").exists()
