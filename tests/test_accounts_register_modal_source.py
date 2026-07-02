from pathlib import Path


ACCOUNTS_TSX = Path("frontend/src/pages/Accounts.tsx")


def test_chatgpt_register_modal_exposes_proxy_pool_and_explicit_proxy_controls():
    source = ACCOUNTS_TSX.read_text(encoding="utf-8")

    assert "chatgptUseProxyPool" in source
    assert "chatgptProxy" in source
    assert "registration_use_proxy_pool" in source
    assert "注册代理（可选，优先于代理池）" in source


def test_chatgpt_workspace_join_blocks_oauth_identity_without_mailbox_context():
    source = ACCOUNTS_TSX.read_text(encoding="utf-8")

    assert "Workspace Join 需要选择系统邮箱" in source
    assert "selection.identityProvider !== 'mailbox'" in source


def test_chatgpt_workspace_join_validation_error_is_rendered_in_register_modal():
    source = ACCOUNTS_TSX.read_text(encoding="utf-8")

    assert "startError" in source
    assert "setStartError" in source
    assert "{startError &&" in source
