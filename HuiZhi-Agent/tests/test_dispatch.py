# -*- coding: utf-8 -*-
"""dispatch.py：6 类意图路由（规则判断）。"""
import dispatch
import store


def _no_store(monkeypatch):
    monkeypatch.setattr(store, "list_profiles", lambda limit=200: [])
    monkeypatch.setattr(store, "list_opportunities", lambda lifecycle=None, db_path=None: [])


def test_route_pipeline(monkeypatch):
    _no_store(monkeypatch)
    r = dispatch.route("帮我跑一遍商机雷达全流程")
    assert r["intent"] == "pipeline"
    assert r["command_hint"] == "/radar"


def test_route_web_search(monkeypatch):
    _no_store(monkeypatch)
    assert dispatch.route("最近外汇管理局有什么新政策")["intent"] == "web_search"


def test_route_visit_pitch(monkeypatch):
    _no_store(monkeypatch)
    r = dispatch.route("帮东鹏饮料生成拜访话术")
    assert r["intent"] == "visit_pitch"
    assert "visit_pitch" in r["suggested_tools"]


def test_route_company_insight(monkeypatch):
    _no_store(monkeypatch)
    assert dispatch.route("东鹏饮料的企业画像")["intent"] == "company_insight"


def test_route_queue_query(monkeypatch):
    _no_store(monkeypatch)
    assert dispatch.route("今天队列有多少条")["intent"] == "queue_query"


def test_route_analyze_company(monkeypatch):
    _no_store(monkeypatch)
    r = dispatch.route("帮我分析东鹏饮料的外汇需求")
    assert r["intent"] == "analyze_company"
    assert "analyze_company" in r["suggested_tools"]


def test_route_fallback(monkeypatch):
    _no_store(monkeypatch)
    assert dispatch.route("今天天气怎么样")["intent"] == "ask"
