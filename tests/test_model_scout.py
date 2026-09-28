from hydra.model_scout import scan_models


def test_model_scout_only_returns_gguf(tmp_path):
    (tmp_path / "model.gguf").write_bytes(b"gguf")
    (tmp_path / "secret.txt").write_text("no")
    models = scan_models(tmp_path)
    assert len(models) == 1
    assert models[0].path == "model.gguf"
