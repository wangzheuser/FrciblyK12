import json

import pytest

from core.base_mailbox import MailboxAccount
from core.local_ms_mailbox import LocalMicrosoftMailboxPool, parse_local_ms_pool_rows


def test_parse_local_ms_pool_rows_accepts_gujumpgate_hotmail_format():
    rows = parse_local_ms_pool_rows(
        "\n".join(
            [
                "account----password----ID----Token",
                "user@example.com----mail-pass----client-id-123----refresh-token-456",
            ]
        )
    )

    assert len(rows) == 1
    entry = rows[0]
    assert entry.email == "user@example.com"
    assert entry.password == "mail-pass"
    assert entry.login_account == "user@example.com"
    assert entry.client_id == "client-id-123"
    assert entry.refresh_token == "refresh-token-456"
    assert entry.source_format == "gujumpgate_hotmail"
    assert entry.graph_ready is True
    assert entry.imap_ready is False


def test_local_ms_pool_records_gujumpgate_source_metadata(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="user@example.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )

    account = pool.get_email()
    provider_account = account.extra["provider_account"]
    provider_resource = account.extra["provider_resource"]

    assert provider_account["credentials"]["client_id"] == "client-id-123"
    assert provider_account["credentials"]["refresh_token"] == "refresh-token-456"
    assert provider_account["metadata"]["source"] == "gujumpgate_hotmail"
    assert provider_resource["metadata"]["source"] == "gujumpgate_hotmail"


def test_local_ms_pool_expands_outlook_plus_alias_slots(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="yourname@outlook.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )

    accounts = [pool.get_email() for _ in range(5)]

    assert [account.email for account in accounts] == [
        "yourname@outlook.com",
        "yourname+1@outlook.com",
        "yourname+2@outlook.com",
        "yourname+3@outlook.com",
        "yourname+4@outlook.com",
    ]
    with pytest.raises(RuntimeError, match="capacity=5"):
        pool.get_email()

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(state["used"]) == {account.email for account in accounts}
    assert state["used"]["yourname+4@outlook.com"]["base_email"] == "yourname@outlook.com"
    assert state["used"]["yourname+4@outlook.com"]["alias_index"] == 4


def test_local_ms_pool_release_alias_allows_retry(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="yourname@outlook.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )

    account = pool.get_email()

    assert account.email == "yourname@outlook.com"
    assert pool.release_email(account, reason="proxy timeout") is True
    assert pool.get_email().email == "yourname@outlook.com"


def test_local_ms_pool_release_ignores_other_providers(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="yourname@outlook.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )
    reserved = pool.get_email()
    other = MailboxAccount(
        email="other@example.com",
        account_id="other@example.com",
        extra={
            "provider_resource": {
                "provider_name": "other_provider",
                "resource_identifier": reserved.account_id,
            }
        },
    )

    assert pool.release_email(other, reason="proxy timeout") is False

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert set(state["used"]) == {reserved.email}


def test_local_ms_pool_alias_account_keeps_base_credentials_for_graph(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="yourname@outlook.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )
    pool.get_email()

    alias_account = pool.get_email()
    provider_account = alias_account.extra["provider_account"]
    provider_resource = alias_account.extra["provider_resource"]
    entry = pool._entry_for_account(alias_account)

    assert alias_account.email == "yourname+1@outlook.com"
    assert provider_account["credentials"]["email"] == "yourname@outlook.com"
    assert provider_account["credentials"]["login_account"] == "yourname@outlook.com"
    assert provider_account["metadata"]["base_email"] == "yourname@outlook.com"
    assert provider_account["metadata"]["alias_email"] == "yourname+1@outlook.com"
    assert provider_account["metadata"]["alias_index"] == 1
    assert provider_resource["handle"] == "yourname+1@outlook.com"
    assert provider_resource["metadata"]["base_email"] == "yourname@outlook.com"
    assert entry.email == "yourname@outlook.com"
    assert entry.client_id == "client-id-123"
    assert entry.refresh_token == "refresh-token-456"


def test_local_ms_pool_does_not_expand_non_microsoft_domains(tmp_path):
    pool = LocalMicrosoftMailboxPool(
        pool_text="user@example.com----mail-pass----client-id-123----refresh-token-456",
        state_file=str(tmp_path / "state.json"),
    )

    assert pool.get_email().email == "user@example.com"
    with pytest.raises(RuntimeError, match="capacity=1"):
        pool.get_email()


def test_graph_access_token_tries_fallback_endpoint(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    def fake_post(url, data, proxies=None, timeout=None):
        calls.append((url, data))
        if len(calls) == 1:
            return FakeResponse(400, text='{"error":"invalid_request"}')
        return FakeResponse(200, {"access_token": "access-token-ok"})

    monkeypatch.setattr("core.local_ms_mailbox.requests.post", fake_post)
    pool = LocalMicrosoftMailboxPool()
    account = MailboxAccount(
        email="user@example.com",
        account_id="user@example.com",
        extra={
            "provider_account": {
                "credentials": {
                    "email": "user@example.com",
                    "client_id": "client-id-123",
                    "refresh_token": "refresh-token-456",
                }
            }
        },
    )
    entry = pool._entry_for_account(account)

    assert pool._graph_access_token(entry) == "access-token-ok"
    assert len(calls) == 2
    assert calls[0][0] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert calls[1][0] == "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
