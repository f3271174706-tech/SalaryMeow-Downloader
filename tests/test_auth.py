"""Authentication token tests."""

from douyin_downloader import main


def test_invite_token_does_not_expose_code(monkeypatch):
    monkeypatch.setattr(main, "DIRECT_INVITE_CODE", "test-invite-code")
    monkeypatch.setattr(main.time, "time", lambda: 1_800_000_000)

    token = main._make_invite_token("test-invite-code")

    assert "test-invite-code" not in token
    assert main._verify_invite_token(token)


def test_expired_invite_token_is_rejected(monkeypatch):
    monkeypatch.setattr(main, "DIRECT_INVITE_CODE", "test-invite-code")
    monkeypatch.setattr(main.time, "time", lambda: 1_800_000_000)
    token = main._make_invite_token("test-invite-code")

    monkeypatch.setattr(main.time, "time", lambda: 1_800_000_000 + 8 * 86400)

    assert not main._verify_invite_token(token)
