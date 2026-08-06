# -*- coding: utf-8 -*-
"""rule_screen.py：classify 标签、排除词过滤、时间窗口过滤。"""
import datetime
import json

import settings
import store
from rule_screen import classify, rule_screen


def _write_crawled(tmp_project, items):
    p = tmp_project / "data" / "crawled" / "test.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def _ann(aid, name, title, date, code="605499"):
    return {
        "id": aid, "stock_code": code, "stock_name": name, "title": title,
        "url": "http://example.com/" + aid, "publish_date": date,
        "source": "巨潮资讯", "keywords_hit": ["套保"], "raw_text": "",
    }


def test_classify_default_keywords():
    tags = classify("关于开展外汇衍生品交易的公告")
    assert "外汇与套保" in tags
    assert "币种待核实" in tags
    tags = classify("关于召开股东大会的通知")
    assert "外汇与套保" not in tags


def test_classify_custom_hedge_keywords():
    # 自定义生效词生效：默认词表不含「增资」，但自定义词表包含则命中
    tags = classify("关于对子公司增资的公告", hedge_keywords=["增资"])
    assert "外汇与套保" in tags
    tags = classify("关于对子公司增资的公告", hedge_keywords=["套保"])
    assert "外汇与套保" not in tags


def test_exclude_words_filter(tmp_project):
    store.init_db()
    _write_crawled(tmp_project, [
        _ann("a1", "拓邦股份", "关于开展外汇套期保值业务的公告", "2026-08-01", code="002139"),
        _ann("a2", "东鹏饮料", "关于开展外汇衍生品交易的公告", "2026-08-01"),
    ])
    settings.save_settings({"exclude_words": ["拓邦股份"]})
    created = rule_screen()
    names = [o["company_name"] for o in created]
    assert "东鹏饮料" in names
    assert "拓邦股份" not in names


def test_days_window_filters_old(tmp_project):
    store.init_db()
    today = datetime.date.today().isoformat()
    old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    _write_crawled(tmp_project, [
        _ann("a1", "东鹏饮料", "关于开展外汇衍生品交易的公告", today),
        _ann("a2", "拓邦股份", "关于开展外汇套期保值业务的公告", old, code="002139"),
    ])
    created = rule_screen()
    names = [o["company_name"] for o in created]
    assert "东鹏饮料" in names
    assert "拓邦股份" not in names
