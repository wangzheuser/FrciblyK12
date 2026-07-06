from __future__ import annotations

import re

from sqlmodel import Session, select

from core.db import ProxyModel, engine
from core.proxy_pool import ProxyPool, materialize_proxy_template, prepare_proxy_url


def test_materialize_proxy_template_replaces_uuid_tokens_consistently():
    proxy = materialize_proxy_template("http://node-{uuid}-{uuid_hex}.proxy:9200")

    match = re.match(
        r"http://node-([0-9a-f-]{36})-([0-9a-f]{32})\.proxy:9200",
        proxy,
    )
    assert match
    assert match.group(1).replace("-", "") == match.group(2)
    assert "{uuid}" not in proxy
    assert "{uuid_hex}" not in proxy


def test_prepare_proxy_url_retries_template_until_probe_passes(monkeypatch):
    probes: list[str] = []

    def fake_probe(proxy_url, **kwargs):
        probes.append(proxy_url)
        if len(probes) < 3:
            raise RuntimeError("proxy node unavailable")

    monkeypatch.setattr("core.proxy_pool.probe_proxy_url", fake_probe)

    proxy = prepare_proxy_url(
        "http://node.{uuid}:admin2012@127.0.0.1:9200",
        max_attempts=99,
    )

    assert len(probes) == 3
    assert proxy == probes[-1]
    assert all("{uuid}" not in item for item in probes)
    assert len(set(probes)) == 3


def test_proxy_pool_get_next_prechecks_template_and_reports_to_source(monkeypatch):
    with Session(engine) as session:
        session.add(ProxyModel(url="http://node.{uuid}:admin2012@127.0.0.1:9200", region="US"))
        session.commit()

    probes: list[str] = []

    def fake_probe(proxy_url, **kwargs):
        probes.append(proxy_url)
        if len(probes) < 2:
            raise RuntimeError("proxy node unavailable")

    monkeypatch.setattr("core.proxy_pool.probe_proxy_url", fake_probe)

    pool = ProxyPool()
    proxy = pool.get_next(region="US", precheck=True, max_attempts=99)

    assert proxy == probes[-1]
    assert proxy.startswith("http://node.")
    assert "{uuid}" not in proxy
    pool.report_success(proxy)

    with Session(engine) as session:
        model = session.exec(select(ProxyModel)).one()
    assert model.success_count == 1
    assert model.fail_count == 0


def test_proxy_pool_get_next_returns_none_when_template_probe_exhausted(monkeypatch):
    with Session(engine) as session:
        session.add(ProxyModel(url="http://node.{uuid}:admin2012@127.0.0.1:9200", region="US"))
        session.commit()

    probes: list[str] = []

    def fake_probe(proxy_url, **kwargs):
        probes.append(proxy_url)
        raise RuntimeError("proxy node unavailable")

    monkeypatch.setattr("core.proxy_pool.probe_proxy_url", fake_probe)

    pool = ProxyPool()
    proxy = pool.get_next(region="US", precheck=True, max_attempts=2)

    assert proxy is None
    assert len(probes) == 2
    with Session(engine) as session:
        model = session.exec(select(ProxyModel)).one()
    assert model.fail_count == 1
