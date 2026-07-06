"""代理池 - 从数据库读取代理，支持轮询、动态模板和按区域选取"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable, Optional, Sequence

import requests
from sqlmodel import Session, select

from .db import ProxyModel, engine
from datetime import datetime, timezone


DEFAULT_PROXY_TEMPLATE_MAX_ATTEMPTS = 99
DEFAULT_PROXY_PROBE_TIMEOUT_SECONDS = 8
DEFAULT_PROXY_PROBE_MAX_RESPONSE_SECONDS = 12
DEFAULT_PROXY_PROBE_URLS = (
    "https://auth.openai.com/api/auth/csrf",
    "https://chatgpt.com/",
)
PROXY_TEMPLATE_TOKENS = ("{uuid}", "{uuid_hex}")


def has_proxy_template(value: str | None) -> bool:
    text = str(value or "")
    return any(token in text for token in PROXY_TEMPLATE_TOKENS)


def materialize_proxy_template(template: str, token: uuid.UUID | None = None) -> str:
    value = token or uuid.uuid4()
    text = str(template or "").strip()
    return text.replace("{uuid}", str(value)).replace("{uuid_hex}", value.hex)


def _proxy_mapping(proxy_url: str) -> dict[str, str]:
    return {"http": proxy_url, "https": proxy_url}


def _mask_proxy(proxy: str | None) -> str:
    value = str(proxy or "").strip()
    if not value or "@" not in value:
        return value
    prefix, _, host = value.rpartition("@")
    scheme, sep, _credentials = prefix.partition("://")
    return f"{scheme}{sep}***@{host}" if sep else f"***@{host}"


def probe_proxy_url(
    proxy_url: str,
    *,
    urls: Sequence[str] | None = None,
    timeout_seconds: int = DEFAULT_PROXY_PROBE_TIMEOUT_SECONDS,
    max_response_seconds: int = DEFAULT_PROXY_PROBE_MAX_RESPONSE_SECONDS,
) -> None:
    """对候选代理执行轻量探测；失败时抛出可读异常。"""
    proxy = str(proxy_url or "").strip()
    if not proxy:
        raise RuntimeError("代理地址为空")
    probe_urls = [str(url or "").strip() for url in (urls or DEFAULT_PROXY_PROBE_URLS) if str(url or "").strip()]
    if not probe_urls:
        raise RuntimeError("代理探测 URL 为空")

    last_error: Exception | None = None
    for url in probe_urls:
        started = time.monotonic()
        try:
            response = requests.get(
                url,
                proxies=_proxy_mapping(proxy),
                timeout=max(int(timeout_seconds or 0), 1),
                allow_redirects=True,
            )
            elapsed = time.monotonic() - started
            if max_response_seconds and elapsed > max_response_seconds:
                raise RuntimeError(f"代理节点响应过慢 {elapsed:.1f}s > {max_response_seconds}s: {url}")
            if int(getattr(response, "status_code", 0) or 0) >= 500:
                raise RuntimeError(f"代理节点探测 HTTP {response.status_code}: {url}")
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error) if last_error else "代理探测失败")


def prepare_proxy_url(
    template: str,
    *,
    probe: bool = True,
    max_attempts: int = DEFAULT_PROXY_TEMPLATE_MAX_ATTEMPTS,
    probe_urls: Sequence[str] | None = None,
    timeout_seconds: int = DEFAULT_PROXY_PROBE_TIMEOUT_SECONDS,
    max_response_seconds: int = DEFAULT_PROXY_PROBE_MAX_RESPONSE_SECONDS,
    renderer: Callable[[str], str] = materialize_proxy_template,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """渲染代理模板；开启 probe 时只返回探测通过的代理。"""
    raw = str(template or "").strip()
    if not raw:
        return ""
    attempts = max(int(max_attempts or 1), 1) if has_proxy_template(raw) else 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        proxy_url = renderer(raw) if has_proxy_template(raw) else raw
        try:
            if probe:
                probe_proxy_url(
                    proxy_url,
                    urls=probe_urls,
                    timeout_seconds=timeout_seconds,
                    max_response_seconds=max_response_seconds,
                )
            return proxy_url
        except Exception as exc:
            last_error = exc
            if callable(log_fn):
                try:
                    log_fn(
                        f"代理预探测失败 {attempt}/{attempts}: "
                        f"{_mask_proxy(proxy_url)} -> {str(exc)[:160]}"
                    )
                except Exception:
                    pass
    raise RuntimeError(f"代理节点预探测失败，已尝试 {attempts} 次: {last_error}")


class ProxyPool:
    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()
        self._rendered_sources: dict[str, str] = {}

    def _remember_rendered_source(self, rendered_url: str, source_url: str) -> None:
        if not rendered_url or rendered_url == source_url:
            return
        with self._lock:
            if len(self._rendered_sources) > 10000:
                self._rendered_sources.clear()
            self._rendered_sources[rendered_url] = source_url

    def _source_url_for_report(self, url: str) -> str:
        value = str(url or "").strip()
        with self._lock:
            return self._rendered_sources.get(value, value)

    def get_next(
        self,
        region: str = "",
        *,
        precheck: bool = False,
        max_attempts: int = DEFAULT_PROXY_TEMPLATE_MAX_ATTEMPTS,
        probe_urls: Sequence[str] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> Optional[str]:
        """获取下一个可用代理。

        优先级:
          1. 动态代理 provider（如果已配置且启用）
          2. 静态代理池里 region 匹配的代理
          3. 静态代理池里**任意**可用代理（软回退——region 不匹配总比无代理强）

        当 ``precheck=True`` 时，动态模板代理会在返回前渲染并探测；探测
        失败会重新渲染，最多 ``max_attempts`` 次。
        """
        # 1. 尝试动态代理
        try:
            from core.proxy_providers import get_dynamic_proxy
            dynamic = get_dynamic_proxy()
            if dynamic:
                try:
                    return prepare_proxy_url(
                        dynamic,
                        probe=precheck,
                        max_attempts=max_attempts,
                        probe_urls=probe_urls,
                        log_fn=log_fn,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # 2/3. 静态代理池：先按 region 严格匹配，没有再回退到任意代理
        with Session(engine) as s:
            all_active = s.exec(
                select(ProxyModel).where(ProxyModel.is_active == True)
            ).all()
            if not all_active:
                return None
            preferred = (
                [p for p in all_active if (p.region or "") == region]
                if region
                else list(all_active)
            )
            pool = preferred if preferred else list(all_active)
            pool.sort(
                key=lambda p: p.success_count / max(p.success_count + p.fail_count, 1),
                reverse=True,
            )
            with self._lock:
                idx = self._index % len(pool)
                self._index += 1
            ordered_pool = list(pool[idx:]) + list(pool[:idx])

        if not precheck:
            selected = ordered_pool[0].url
            rendered = materialize_proxy_template(selected) if has_proxy_template(selected) else selected
            self._remember_rendered_source(rendered, selected)
            return rendered

        for item in ordered_pool:
            source_url = str(item.url or "").strip()
            if not source_url:
                continue
            try:
                resolved = prepare_proxy_url(
                    source_url,
                    probe=True,
                    max_attempts=max_attempts,
                    probe_urls=probe_urls,
                    log_fn=log_fn,
                )
                self._remember_rendered_source(resolved, source_url)
                return resolved
            except Exception:
                self.report_fail(source_url)
                continue
        return None

    def report_success(self, url: str) -> None:
        source_url = self._source_url_for_report(url)
        with Session(engine) as s:
            p = s.exec(select(ProxyModel).where(ProxyModel.url == source_url)).first()
            if p:
                p.success_count += 1
                p.last_checked = datetime.now(timezone.utc)
                s.add(p)
                s.commit()

    def report_fail(self, url: str) -> None:
        source_url = self._source_url_for_report(url)
        with Session(engine) as s:
            p = s.exec(select(ProxyModel).where(ProxyModel.url == source_url)).first()
            if p:
                p.fail_count += 1
                p.last_checked = datetime.now(timezone.utc)
                # 连续失败超过10次自动禁用
                if p.fail_count > 0 and p.success_count == 0 and p.fail_count >= 5:
                    p.is_active = False
                s.add(p)
                s.commit()

    def check_all(self) -> dict:
        """检测所有代理可用性"""
        with Session(engine) as s:
            proxies = s.exec(select(ProxyModel)).all()
        results = {"ok": 0, "fail": 0}
        for p in proxies:
            try:
                prepare_proxy_url(
                    p.url,
                    probe=True,
                    max_attempts=3,
                    probe_urls=("https://httpbin.org/ip",),
                )
                self.report_success(p.url)
                results["ok"] += 1
                continue
            except Exception:
                pass
            self.report_fail(p.url)
            results["fail"] += 1
        return results


proxy_pool = ProxyPool()
