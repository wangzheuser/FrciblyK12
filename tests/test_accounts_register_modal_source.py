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


def test_chatgpt_workspace_ids_default_to_empty_and_have_no_builtin_ids():
    source = ACCOUNTS_TSX.read_text(encoding="utf-8")

    assert "const DEFAULT_CHATGPT_WORKSPACE_IDS = ''" in source
    assert "631e1603-06cf-4f0b-b79b-d09fbfcfe98d" not in source
    assert "d1869eec-4d2d-4fce-967f-a1a6b906d51e" not in source
    assert "留空时不加入 Workspace，仅导出 free 账号 CPA JSON" in source
