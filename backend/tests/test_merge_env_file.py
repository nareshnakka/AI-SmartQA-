import importlib.util
from pathlib import Path


def _load_merge_mod():
    path = Path(__file__).resolve().parents[1] / "scripts" / "merge_env_file.py"
    spec = importlib.util.spec_from_file_location("merge_env_file", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merge_env_adds_missing_and_keeps_secrets():
    mod = _load_merge_mod()
    base = "A=keep-me\nB=\n"
    incoming = "A=from-repo\nB=filled\nC=new\n"
    merged, keys = mod.merge_env_texts(base, incoming)
    assert "A=keep-me" in merged
    assert "B=filled" in merged
    assert "C=new" in merged
    assert any("B" in k for k in keys)
    assert "C" in keys


def test_merge_env_files(tmp_path):
    mod = _load_merge_mod()
    local = tmp_path / ".env"
    repo = tmp_path / "incoming.env"
    local.write_text("SECRET=local-secret\nOLD=\n", encoding="utf-8")
    repo.write_text("SECRET=should-not-win\nOLD=from-repo\nNEW=1\n", encoding="utf-8")
    result = mod.merge_env_files(local, repo)
    assert result["changed"] is True
    text = local.read_text(encoding="utf-8")
    assert "SECRET=local-secret" in text
    assert "OLD=from-repo" in text
    assert "NEW=1" in text
