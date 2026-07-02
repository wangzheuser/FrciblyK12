from platforms._browser_backend import BrowserBackendConfig
import platforms.chatgpt.browser_register as browser_register_module
from platforms.chatgpt.browser_register import (
    _apply_camoufox_visible_window_limit,
    _browser_registration_flow,
    _click_about_you_submit,
    _email_otp_page_has_visible_code_input,
    _install_websocket_blocker,
    _new_browser_page,
    _submit_otp_via_page,
)


def test_apply_camoufox_visible_window_limit_sets_1280_by_720_window_for_headed_camoufox():
    launch_opts = {"headless": False}

    _apply_camoufox_visible_window_limit(
        launch_opts,
        BrowserBackendConfig.camoufox(headless=False),
    )

    assert launch_opts["window"] == (1280, 720)


def test_apply_camoufox_visible_window_limit_skips_headless_camoufox():
    launch_opts = {"headless": True}

    _apply_camoufox_visible_window_limit(
        launch_opts,
        BrowserBackendConfig.camoufox(headless=True),
    )

    assert "window" not in launch_opts


def test_apply_camoufox_visible_window_limit_skips_bitbrowser():
    launch_opts = {"headless": False}

    _apply_camoufox_visible_window_limit(
        launch_opts,
        BrowserBackendConfig.bitbrowser(profile_id="profile-1"),
    )

    assert "window" not in launch_opts


def test_new_browser_page_disables_default_viewport_for_camoufox_protocol_compat():
    class _Browser:
        def __init__(self):
            self.calls = []

        def new_page(self, **kwargs):
            self.calls.append(kwargs)
            return "page"

    browser = _Browser()

    assert _new_browser_page(browser) == "page"
    assert browser.calls == [{"no_viewport": True}]


def test_new_browser_page_falls_back_for_wrappers_without_no_viewport_argument():
    class _Browser:
        def __init__(self):
            self.calls = []

        def new_page(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if kwargs:
                raise TypeError("unexpected keyword argument")
            return "page"

    browser = _Browser()

    assert _new_browser_page(browser) == "page"
    assert browser.calls == [((), {"no_viewport": True}), ((), {})]


def test_browser_registration_skips_explicit_email_otp_send_when_code_input_is_ready(monkeypatch):
    calls = []

    class _Context:
        def add_cookies(self, cookies):
            calls.append("seed_cookies")

    class _Page:
        url = "https://auth.openai.com/email-verification"
        context = _Context()

        def evaluate(self, script):
            if "navigator.userAgent" in str(script):
                return "Mozilla/5.0 Chrome/136.0"
            return None

    monkeypatch.setattr(
        browser_register_module,
        "_start_browser_signup_via_authorize",
        lambda page, email, device_id, log: {
            "page_type": "email_otp_verification",
            "method": "GET",
            "continue_url": "",
            "current_url": page.url,
        },
    )
    monkeypatch.setattr(browser_register_module, "_get_cookies", lambda page: {"login_session": "yes", "oai-did": "yes"})
    monkeypatch.setattr(browser_register_module, "_handle_post_signup_onboarding", lambda page, log: None)
    monkeypatch.setattr(
        browser_register_module,
        "_is_registration_complete",
        lambda state: state.get("page_type") == "chatgpt_home",
    )
    monkeypatch.setattr(
        browser_register_module,
        "_extract_flow_state",
        lambda data, url: {"page_type": "chatgpt_home", "method": "GET", "continue_url": "", "current_url": url},
    )
    monkeypatch.setattr(browser_register_module, "_email_otp_page_has_visible_code_input", lambda page: True)

    def _send_email_otp(page):
        raise AssertionError("验证码输入框已就绪时不应额外调用 email-otp/send，以免刷新 auth session")

    def _otp_callback():
        calls.append("wait_mailbox_code")
        return "123456"

    def _submit_otp(page, code, log):
        calls.append(f"submit_otp:{code}")
        return {"ok": True, "status": 200, "url": "https://chatgpt.com/", "data": None, "text": ""}

    monkeypatch.setattr(browser_register_module, "_send_browser_email_otp", _send_email_otp)
    monkeypatch.setattr(browser_register_module, "_submit_otp_via_page", _submit_otp)

    _browser_registration_flow(_Page(), "user@example.com", "Password123!", _otp_callback, None, lambda message: calls.append(f"log:{message}"))

    assert "submit_otp:123456" in calls
    assert any("页面已显示验证码输入框" in call for call in calls)


def test_browser_registration_sends_email_otp_when_code_input_is_not_ready(monkeypatch):
    calls = []

    class _Context:
        def add_cookies(self, cookies):
            calls.append("seed_cookies")

    class _Page:
        url = "https://auth.openai.com/email-verification"
        context = _Context()

        def evaluate(self, script):
            if "navigator.userAgent" in str(script):
                return "Mozilla/5.0 Chrome/136.0"
            return None

    monkeypatch.setattr(
        browser_register_module,
        "_start_browser_signup_via_authorize",
        lambda page, email, device_id, log: {
            "page_type": "email_otp_verification",
            "method": "GET",
            "continue_url": "",
            "current_url": page.url,
        },
    )
    monkeypatch.setattr(browser_register_module, "_get_cookies", lambda page: {"login_session": "yes", "oai-did": "yes"})
    monkeypatch.setattr(browser_register_module, "_handle_post_signup_onboarding", lambda page, log: None)
    monkeypatch.setattr(
        browser_register_module,
        "_is_registration_complete",
        lambda state: state.get("page_type") == "chatgpt_home",
    )
    monkeypatch.setattr(
        browser_register_module,
        "_extract_flow_state",
        lambda data, url: {"page_type": "chatgpt_home", "method": "GET", "continue_url": "", "current_url": url},
    )
    monkeypatch.setattr(browser_register_module, "_email_otp_page_has_visible_code_input", lambda page: False)

    def _send_email_otp(page):
        calls.append("send_email_otp")
        return {"ok": True, "status": 200, "text": ""}

    def _otp_callback():
        calls.append("wait_mailbox_code")
        return "123456"

    def _submit_otp(page, code, log):
        calls.append(f"submit_otp:{code}")
        return {"ok": True, "status": 200, "url": "https://chatgpt.com/", "data": None, "text": ""}

    monkeypatch.setattr(browser_register_module, "_send_browser_email_otp", _send_email_otp)
    monkeypatch.setattr(browser_register_module, "_submit_otp_via_page", _submit_otp)

    _browser_registration_flow(_Page(), "user@example.com", "Password123!", _otp_callback, None, lambda message: calls.append(f"log:{message}"))

    assert calls.index("send_email_otp") < calls.index("wait_mailbox_code")
    assert "submit_otp:123456" in calls


def test_email_otp_page_has_visible_code_input_detects_ready_page():
    class _Page:
        def evaluate(self, script):
            return True

    assert _email_otp_page_has_visible_code_input(_Page()) is True


def test_email_otp_page_has_visible_code_input_returns_false_on_probe_error():
    class _Page:
        def evaluate(self, script):
            raise RuntimeError("dom not ready")

    assert _email_otp_page_has_visible_code_input(_Page()) is False


def test_click_about_you_submit_uses_dom_request_submit_when_click_helper_times_out(monkeypatch):
    calls = []

    class _Page:
        def evaluate(self, script):
            calls.append("dom_submit")
            return {"ok": True, "text": "Termina de crear tu cuenta"}

    monkeypatch.setattr(browser_register_module, "_click_first_no_wait", lambda *args, **kwargs: None)

    selector = _click_about_you_submit(_Page(), lambda message: calls.append(f"log:{message}"))

    assert selector == "dom:Termina de crear tu cuenta"
    assert "dom_submit" in calls


def test_install_websocket_blocker_aborts_websocket_requests():
    captured = {}

    class _Page:
        def route(self, pattern, handler):
            captured["pattern"] = pattern
            captured["handler"] = handler

    class _Request:
        resource_type = "websocket"
        url = "wss://chatgpt.com/backend-api/realtime"

    class _Route:
        request = _Request()

        def __init__(self):
            self.actions = []

        def abort(self):
            self.actions.append("abort")

        def continue_(self):
            self.actions.append("continue")

    _install_websocket_blocker(_Page(), lambda _message: None)

    route = _Route()
    captured["handler"](route)

    assert captured["pattern"] == "**/*"
    assert route.actions == ["abort"]


def test_submit_otp_via_page_falls_back_to_email_otp_api_when_inputs_are_not_visible(monkeypatch):
    calls = []

    class _MissingLocator:
        @property
        def first(self):
            return self

        def count(self):
            return 0

        def wait_for(self, *args, **kwargs):
            raise TimeoutError("not visible")

        def is_visible(self, *args, **kwargs):
            return False

    class _Page:
        url = "https://auth.openai.com/email-verification"

        def wait_for_load_state(self, *args, **kwargs):
            calls.append("wait_load")

        def locator(self, selector):
            calls.append(f"locator:{selector}")
            return _MissingLocator()

        def get_by_label(self, pattern):
            calls.append("get_by_label")
            return _MissingLocator()

        def get_by_role(self, role, name=None):
            calls.append(f"get_by_role:{role}")
            return _MissingLocator()

        def evaluate(self, script):
            if "navigator.userAgent" in str(script):
                return "Mozilla/5.0 Chrome/136.0"
            return None

    validate_calls = {"count": 0}

    def _validate(page, code, device_id, user_agent, referer):
        validate_calls["count"] += 1
        calls.append(("api_validate", code, device_id, user_agent, referer))
        return {
            "ok": True,
            "status": 200,
            "url": "https://auth.openai.com/email-verification",
            "data": {"continue_url": "/about-you"},
            "text": "",
        }

    monkeypatch.setattr(browser_register_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_register_module, "_get_cookies", lambda page: {"oai-did": "device-1"})
    monkeypatch.setattr(browser_register_module, "_validate_browser_email_otp", _validate)

    result = _submit_otp_via_page(_Page(), "123456", lambda message: calls.append(f"log:{message}"))

    assert result["ok"] is True
    assert result["status"] == 200
    assert validate_calls["count"] == 1
    assert ("api_validate", "123456", "device-1", "Mozilla/5.0 Chrome/136.0", "https://auth.openai.com/email-verification") in calls
    assert "log:验证码页未发现可见输入框，改用 email-otp validate 接口提交" in calls


def test_submit_otp_via_page_uses_ui_before_email_otp_api(monkeypatch):
    calls = []

    class _MissingLocator:
        @property
        def first(self):
            return self

        def count(self):
            return 0

        def wait_for(self, *args, **kwargs):
            raise TimeoutError("not visible")

        def is_visible(self, *args, **kwargs):
            return False

        def text_content(self, *args, **kwargs):
            return ""

    class _OtpLocator:
        @property
        def first(self):
            return self

        def wait_for(self, *args, **kwargs):
            calls.append("otp_wait")

        def click(self, *args, **kwargs):
            calls.append("otp_click")

        def fill(self, value):
            calls.append(f"otp_fill:{value}")

        def type(self, value, **kwargs):
            calls.append(f"otp_type:{value}")

        def input_value(self):
            return "123456"

    class _Page:
        url = "https://auth.openai.com/email-verification"

        def wait_for_load_state(self, *args, **kwargs):
            calls.append("wait_load")

        def locator(self, selector):
            calls.append(f"locator:{selector}")
            return _MissingLocator()

        def get_by_label(self, pattern):
            calls.append("get_by_label")
            return _OtpLocator()

        def get_by_role(self, role, name=None):
            calls.append(f"get_by_role:{role}")
            return _MissingLocator()

        def evaluate(self, script):
            if "navigator.userAgent" in str(script):
                return "Mozilla/5.0 Chrome/136.0"
            return None

    def _validate(page, code, device_id, user_agent, referer):
        raise AssertionError("可见 OTP 输入框存在时应先走页面表单提交，不应优先调用 API validate")

    monkeypatch.setattr(browser_register_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_register_module.time, "time", lambda: 0)
    monkeypatch.setattr(browser_register_module, "_browser_pause", lambda *args, **kwargs: None)

    def _click_first(page, selectors, timeout=8):
        calls.append("click_submit")
        page.url = "https://auth.openai.com/about-you"
        return 'button[type="submit"]'

    monkeypatch.setattr(browser_register_module, "_click_first", _click_first)
    monkeypatch.setattr(browser_register_module, "_get_cookies", lambda page: {"oai-did": "device-1"})
    monkeypatch.setattr(browser_register_module, "_validate_browser_email_otp", _validate)

    result = _submit_otp_via_page(_Page(), "123456", lambda message: calls.append(f"log:{message}"))

    assert result["ok"] is True
    assert result["url"] == "https://auth.openai.com/about-you"
    assert "click_submit" in calls


def test_submit_otp_via_page_falls_back_to_email_otp_api_when_ui_submit_does_not_advance(monkeypatch):
    calls = []

    class _MissingLocator:
        @property
        def first(self):
            return self

        def count(self):
            return 0

        def wait_for(self, *args, **kwargs):
            raise TimeoutError("not visible")

        def is_visible(self, *args, **kwargs):
            return False

    class _OtpLocator:
        @property
        def first(self):
            return self

        def wait_for(self, *args, **kwargs):
            calls.append("otp_wait")

        def click(self, *args, **kwargs):
            calls.append("otp_click")

        def fill(self, value):
            calls.append(f"otp_fill:{value}")

        def type(self, value, **kwargs):
            calls.append(f"otp_type:{value}")

        def input_value(self):
            return "123456"

    class _Page:
        url = "https://auth.openai.com/email-verification"

        def wait_for_load_state(self, *args, **kwargs):
            calls.append("wait_load")

        def locator(self, selector):
            calls.append(f"locator:{selector}")
            if selector == "text=Invalid code":
                return _MissingLocator()
            return _MissingLocator()

        def get_by_label(self, pattern):
            calls.append("get_by_label")
            return _OtpLocator()

        def get_by_role(self, role, name=None):
            calls.append(f"get_by_role:{role}")
            return _MissingLocator()

        def evaluate(self, script):
            if "navigator.userAgent" in str(script):
                return "Mozilla/5.0 Chrome/136.0"
            return None

    validate_calls = {"count": 0}

    def _validate(page, code, device_id, user_agent, referer):
        validate_calls["count"] += 1
        calls.append(("api_validate", code, device_id, user_agent, referer))
        return {
            "ok": True,
            "status": 200,
            "url": "https://auth.openai.com/email-verification",
            "data": {"continue_url": "/about-you"},
            "text": "",
        }

    times = iter([0, 21])

    monkeypatch.setattr(browser_register_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_register_module.time, "time", lambda: next(times, 21))
    monkeypatch.setattr(browser_register_module, "_browser_pause", lambda *args, **kwargs: None)
    monkeypatch.setattr(browser_register_module, "_click_first", lambda *args, **kwargs: 'button[type="submit"]')
    monkeypatch.setattr(browser_register_module, "_get_cookies", lambda page: {"oai-did": "device-1"})
    monkeypatch.setattr(browser_register_module, "_validate_browser_email_otp", _validate)

    result = _submit_otp_via_page(_Page(), "123456", lambda message: calls.append(f"log:{message}"))

    assert result["ok"] is True
    assert result["status"] == 200
    assert validate_calls["count"] == 1
    assert ("api_validate", "123456", "device-1", "Mozilla/5.0 Chrome/136.0", "https://auth.openai.com/email-verification") in calls
    assert "log:验证码页提交后未跳转，改用 email-otp validate 接口提交" in calls
