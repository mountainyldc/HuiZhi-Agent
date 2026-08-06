# -*- coding: utf-8 -*-
"""store.py：画像/记忆/公告/商机 的 upsert/get 与生命周期。"""
import store


def _ann(aid, name, title, date="2026-08-01"):
    return {
        "id": aid, "stock_code": "605499", "stock_name": name, "title": title,
        "url": "http://example.com/" + aid, "publish_date": date,
        "source": "巨潮资讯", "keywords_hit": ["套保"], "raw_text": "",
    }


def test_insights_upsert_get_list(tmp_project):
    store.init_db()
    store.upsert_insight({
        "company": "测试公司",
        "revenue_scale": '{"value": "约1亿", "source": "年报", "date": "2026-01-01"}',
        "export_ratio": '{"value": "未披露"}',
        "overseas_subsidiaries": "", "fx_exposure_direction": "",
        "hedge_history": "", "recommended_products": "",
        "confidence": "中", "source_note": "测试", "updated_at": "2026-08-06",
    })
    got = store.get_insight("测试公司")
    assert got is not None and got["confidence"] == "中"
    assert "revenue_scale" in got
    assert any(i["company"] == "测试公司" for i in store.list_insights())


def test_memory_set_get(tmp_project):
    store.init_db()
    store.memory_set({"recent_companies": ["东鹏饮料"], "last_company": "东鹏饮料", "regions": ["深圳"]})
    m = store.memory_get()
    assert m["last_company"] == "东鹏饮料"
    assert m["regions"] == ["深圳"]
    store.memory_set({"recent_companies": [], "last_company": None, "regions": []})
    assert store.memory_get()["last_company"] is None


def test_announcements_upsert_list(tmp_project):
    store.init_db()
    store.upsert_announcements([_ann("a1", "东鹏饮料", "关于开展外汇衍生品交易的公告")])
    anns = store.list_announcements()
    assert len(anns) == 1
    assert anns[0]["stock_name"] == "东鹏饮料"
    assert anns[0]["keywords_hit"] == ["套保"]


def test_opportunity_lifecycle(tmp_project):
    store.init_db()
    opp = {
        "id": "opp_test1", "announcement_id": "a1", "company_name": "东鹏饮料",
        "city": "深圳", "tags": ["外汇与套保"], "trigger_event": "巨潮公告：套保",
        "rule_hits": ["广东企业"], "score": 80, "score_breakdown": {},
        "lifecycle": "new", "owner": None, "created_date": "2026-08-06",
        "biz": {"biz_type": "汇率避险"},
    }
    store.insert_opportunity(opp)
    got = store.get_opportunity("opp_test1")
    assert got["lifecycle"] == "new"
    store.set_lifecycle("opp_test1", "verifying", owner="叶霖德")
    got = store.get_opportunity("opp_test1")
    assert got["lifecycle"] == "verifying" and got["owner"] == "叶霖德"
    lst = store.list_opportunities()
    assert any(o["id"] == "opp_test1" for o in lst)
