from core.base_mailbox import _extract_verification_link
from platforms.chatgpt.workspace_join import (
    DEFAULT_WORKSPACE_IDS,
    open_workspace_invite_in_browser,
    parse_workspace_ids,
    request_workspace_join_in_browser,
    run_workspace_join_flow,
)


def test_parse_workspace_ids_uses_default_when_blank():
    assert parse_workspace_ids("") == parse_workspace_ids(DEFAULT_WORKSPACE_IDS)


def test_parse_workspace_ids_accepts_commas_and_lines():
    assert parse_workspace_ids(" one,\ntwo \n\n three ") == ["one", "two", "three"]


def test_extract_verification_link_accepts_chatgpt_workspace_invite():
    html = """
    <a href="https://chatgpt.com/k12-invite?inv_ws_name=w&amp;wId=d1869eec-4d2d-4fce-967f-a1a6b906d51e&amp;aiId=abc">
      Join workspace
    </a>
    """

    assert _extract_verification_link(html, "k12-invite") == (
        "https://chatgpt.com/k12-invite?inv_ws_name=w"
        "&wId=d1869eec-4d2d-4fce-967f-a1a6b906d51e&aiId=abc"
    )


def test_open_workspace_invite_requires_clicking_invite_button():
    class FakePage:
        def __init__(self):
            self.url = ""

        def goto(self, url, **_kwargs):
            self.url = url

        def wait_for_timeout(self, _ms):
            return None

        def evaluate(self, _script):
            return {"clicked": False, "text": "", "url": self.url}

    result = open_workspace_invite_in_browser(
        FakePage(),
        "https://chatgpt.com/k12-invite?wId=workspace-1&aiId=invite-1",
    )

    assert result["ok"] is False
    assert result["clicked"] is False
    assert "invite" in result["error"]


def test_open_workspace_invite_recognizes_go_to_teachers_button():
    button_text = "\u8f6c\u81f3 ChatGPT for Teachers"

    class FakePage:
        def __init__(self):
            self.url = ""

        def goto(self, url, **_kwargs):
            self.url = url

        def wait_for_timeout(self, _ms):
            return None

        def evaluate(self, script):
            clicked = "\u8f6c\u81f3\\s*ChatGPT\\s*for\\s*Teachers" in script
            return {
                "clicked": clicked,
                "text": button_text if clicked else "",
                "url": self.url,
            }

    result = open_workspace_invite_in_browser(
        FakePage(),
        "https://chatgpt.com/k12-invite?wId=workspace-1&aiId=invite-1",
    )

    assert result["ok"] is True
    assert result["clicked"] is True
    assert result["clicked_text"] == button_text


def test_open_workspace_invite_waits_for_late_invite_button():
    class FakePage:
        def __init__(self):
            self.url = ""
            self.evaluate_calls = 0

        def goto(self, url, **_kwargs):
            self.url = url

        def wait_for_timeout(self, _ms):
            return None

        def evaluate(self, _script):
            self.evaluate_calls += 1
            if self.evaluate_calls < 3:
                return {"clicked": False, "text": "", "url": self.url}
            return {
                "clicked": True,
                "text": "转至 ChatGPT for Teachers",
                "url": self.url,
            }

    page = FakePage()
    result = open_workspace_invite_in_browser(
        page,
        "https://chatgpt.com/k12-invite?wId=workspace-1&aiId=invite-1",
    )

    assert result["ok"] is True
    assert result["clicked"] is True
    assert page.evaluate_calls == 3


def test_request_workspace_join_falls_back_to_direct_http_when_page_driver_is_unusable(monkeypatch):
    import platforms.chatgpt.workspace_join as workspace_join

    class FakePage:
        url = "https://chatgpt.com/"

        def evaluate(self, *_args, **_kwargs):
            raise RuntimeError("Connection closed while reading from the driver")

    class FakeResponse:
        status_code = 200
        ok = True
        url = "https://chatgpt.com/backend-api/accounts/workspace-1/invites/request"
        text = "{}"

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(workspace_join.requests, "post", fake_post)

    logs: list[str] = []
    result = request_workspace_join_in_browser(
        FakePage(),
        access_token="registration-access",
        workspace_ids=["workspace-1"],
        log=logs.append,
    )

    assert result == [
        {
            "ok": True,
            "status": 200,
            "url": "https://chatgpt.com/backend-api/accounts/workspace-1/invites/request",
            "text": "{}",
            "workspace_id": "workspace-1",
        }
    ]
    assert captured["url"].endswith("/backend-api/accounts/workspace-1/invites/request")
    assert captured["kwargs"]["headers"]["authorization"] == "Bearer registration-access"
    assert any("direct HTTP fallback" in item for item in logs)


def test_request_workspace_join_does_not_retry_same_domain_rejection():
    class FakePage:
        url = "https://chatgpt.com/"

        def __init__(self):
            self.evaluate_calls = 0

        def evaluate(self, *_args, **_kwargs):
            self.evaluate_calls += 1
            if self.evaluate_calls == 1:
                return {"ok": True, "status": 200, "accessToken": "page-access", "text": ""}
            return {
                "ok": False,
                "status": 401,
                "url": "https://chatgpt.com/backend-api/accounts/workspace-1/invites/request",
                "text": '{"detail":"Only users with emails on the same domain can request access to a workspace"}',
            }

    page = FakePage()
    result = request_workspace_join_in_browser(
        page,
        access_token="registration-access",
        workspace_ids=["workspace-1"],
        max_retries=3,
    )

    assert result[0]["status"] == 401
    assert page.evaluate_calls == 2


def test_request_workspace_join_can_stop_after_first_success():
    class FakePage:
        url = "https://chatgpt.com/"

        def __init__(self):
            self.requested: list[str] = []

        def evaluate(self, _script, arg=None):
            if arg is None:
                return {"ok": True, "status": 200, "accessToken": "page-access", "text": ""}
            self.requested.append(arg["wsId"])
            return {
                "ok": True,
                "status": 200,
                "url": f"https://chatgpt.com/backend-api/accounts/{arg['wsId']}/invites/request",
                "text": '{"success":true}',
            }

    page = FakePage()
    result = request_workspace_join_in_browser(
        page,
        workspace_ids=["workspace-1", "workspace-2"],
        stop_after_first_success=True,
    )

    assert [item["workspace_id"] for item in result] == ["workspace-1"]
    assert page.requested == ["workspace-1"]


def test_workspace_join_flow_exports_cpa_and_returns_workspace_credentials(monkeypatch, tmp_path):
    import platforms.chatgpt.workspace_join as workspace_join

    class FakeMailbox:
        def get_current_ids(self, _account):
            return set()

        def wait_for_link(self, *_args, **_kwargs):
            return "https://chatgpt.com/k12-invite?wId=workspace-1&aiId=invite-1"

    monkeypatch.setattr(
        workspace_join,
        "request_workspace_join_in_browser",
        lambda *_args, **_kwargs: [{"ok": True, "workspace_id": "workspace-1"}],
    )
    monkeypatch.setattr(
        workspace_join,
        "open_workspace_invite_in_browser",
        lambda *_args, **_kwargs: {"ok": True, "clicked": True},
    )
    monkeypatch.setattr(
        workspace_join,
        "export_workspace_cpa_session_from_browser",
        lambda *_args, **_kwargs: {
            "ok": True,
            "path": str(tmp_path / "member.json"),
            "email": "member@example.com",
            "account_id": "workspace-account",
            "expired": "2026-07-01T00:00:00Z",
            "access_token": "workspace-access",
            "refresh_token": "",
            "id_token": "workspace-id",
            "session_token": "workspace-session",
        },
        raising=False,
    )

    result = run_workspace_join_flow(
        object(),
        {"access_token": "registration-access"},
        mailbox=FakeMailbox(),
        mailbox_account=object(),
        config={
            "workspace_ids": "workspace-1",
            "accept_invite": True,
            "export_cpa_json": True,
            "cpa_output_dir": str(tmp_path),
        },
    )

    assert result["access_token"] == "workspace-access"
    assert result["id_token"] == "workspace-id"
    assert result["session_token"] == "workspace-session"
    assert result["account_id"] == "workspace-account"
    assert result["workspace_join"]["cpa_export"]["path"].endswith("member.json")


def test_workspace_join_flow_uses_first_successful_workspace_and_existing_invite(monkeypatch, tmp_path):
    import platforms.chatgpt.workspace_join as workspace_join

    class FakeMailbox:
        def __init__(self):
            self.calls: list[dict] = []

        def get_current_ids(self, _account):
            return {"old-message"}

        def wait_for_link(self, *_args, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("before_ids"):
                raise TimeoutError("no fresh invite")
            return "https://chatgpt.com/k12-invite?wId=workspace-2&aiId=invite-2"

    mailbox = FakeMailbox()
    exported: dict[str, str] = {}

    def fake_request(*_args, **kwargs):
        assert kwargs["stop_after_first_success"] is True
        return [
            {"ok": False, "workspace_id": "workspace-1", "status": 401},
            {"ok": True, "workspace_id": "workspace-2", "status": 200},
        ]

    def fake_export(*_args, **kwargs):
        exported["workspace_id"] = kwargs["workspace_id"]
        return {
            "ok": True,
            "path": str(tmp_path / "member.json"),
            "email": "member@example.com",
            "account_id": "workspace-account",
            "expired": "2026-07-01T00:00:00Z",
            "access_token": "workspace-access",
            "refresh_token": "",
            "id_token": "workspace-id",
            "session_token": "workspace-session",
        }

    monkeypatch.setattr(workspace_join, "request_workspace_join_in_browser", fake_request)
    monkeypatch.setattr(
        workspace_join,
        "open_workspace_invite_in_browser",
        lambda *_args, **_kwargs: {"ok": True, "clicked": True},
    )
    monkeypatch.setattr(
        workspace_join,
        "export_workspace_cpa_session_from_browser",
        fake_export,
        raising=False,
    )

    result = run_workspace_join_flow(
        object(),
        {"access_token": "registration-access"},
        mailbox=mailbox,
        mailbox_account=object(),
        config={
            "workspace_ids": "workspace-1\nworkspace-2",
            "accept_invite": True,
            "export_cpa_json": True,
            "invite_timeout": 1,
            "cpa_output_dir": str(tmp_path),
        },
    )

    assert result["workspace_join"]["ok"] is True
    assert result["workspace_id"] == "workspace-2"
    assert exported["workspace_id"] == "workspace-2"
    assert len(mailbox.calls) == 2
    assert mailbox.calls[0]["before_ids"] == {"old-message"}
    assert mailbox.calls[1]["before_ids"] == set()


def test_workspace_join_flow_fails_when_cpa_export_fails(monkeypatch, tmp_path):
    import platforms.chatgpt.workspace_join as workspace_join

    class FakeMailbox:
        def get_current_ids(self, _account):
            return set()

        def wait_for_link(self, *_args, **_kwargs):
            return "https://chatgpt.com/k12-invite?wId=workspace-1&aiId=invite-1"

    logs: list[str] = []
    monkeypatch.setattr(
        workspace_join,
        "request_workspace_join_in_browser",
        lambda *_args, **_kwargs: [{"ok": True, "workspace_id": "workspace-1"}],
    )
    monkeypatch.setattr(
        workspace_join,
        "open_workspace_invite_in_browser",
        lambda *_args, **_kwargs: {"ok": True, "clicked": True},
    )

    def fail_export(*_args, **_kwargs):
        raise RuntimeError("workspace switch failed")

    monkeypatch.setattr(
        workspace_join,
        "export_workspace_cpa_session_from_browser",
        fail_export,
        raising=False,
    )

    result = run_workspace_join_flow(
        object(),
        {"access_token": "registration-access"},
        mailbox=FakeMailbox(),
        mailbox_account=object(),
        config={
            "workspace_ids": "workspace-1",
            "accept_invite": True,
            "export_cpa_json": True,
            "cpa_output_dir": str(tmp_path),
        },
        log=logs.append,
    )

    assert result["workspace_join"]["ok"] is False
    assert result["workspace_join"]["error"] == (
        "CPA JSON export failed: workspace switch failed"
    )
    assert result["workspace_join"]["cpa_export"] == {
        "ok": False,
        "error": "workspace switch failed",
    }
    assert any("CPA JSON export failed" in item for item in logs)
