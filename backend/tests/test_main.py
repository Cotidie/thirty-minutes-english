import importlib


def test_importing_the_app_module_opens_no_database(tmp_path, monkeypatch):
    path = tmp_path / "never.db"
    monkeypatch.setenv("DB_PATH", str(path))
    import app.main

    importlib.reload(app.main)
    assert not path.exists()
