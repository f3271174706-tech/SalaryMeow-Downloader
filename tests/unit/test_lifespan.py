from app import lifespan


def test_prewarm_f2_loads_required_modules(monkeypatch) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(lifespan.importlib, "import_module", loaded.append)

    lifespan.prewarm_f2()

    assert loaded == [
        "f2.apps.douyin.crawler",
        "f2.apps.douyin.model",
        "f2.apps.douyin.utils",
    ]
