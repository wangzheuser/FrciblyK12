from tools.patch_playwright_firefox_driver import PAGE_ERROR_OLD, WEBSOCKET_OLD, patch_text


def test_patch_text_guards_firefox_pageerror_and_websocket_assertions():
    original = f"{PAGE_ERROR_OLD}\n{WEBSOCKET_OLD}"

    patched, changed = patch_text(original)

    assert changed is True
    assert "const location = pageError.location || {};" in patched
    assert "url: location.url || \"\"" in patched
    assert "if (!request2)" in patched
    assert "if (!response2)" in patched
