# -*- coding: utf-8 -*-
"""settings.py：关键词/排除词/时间窗口的读写、回退与恢复默认。"""
import settings


def test_defaults_when_no_file(tmp_project):
    assert settings.get_settings() == settings.DEFAULTS
    assert settings.exclude_words() == []


def test_save_get_roundtrip(tmp_project):
    settings.save_settings({"keywords": ["套保", "远期结售汇"], "exclude_words": ["更正"], "days_window": 90})
    s = settings.get_settings()
    assert s["keywords"] == ["套保", "远期结售汇"]
    assert s["exclude_words"] == ["更正"]
    assert s["days_window"] == 90


def test_reset_restores_defaults(tmp_project):
    settings.save_settings({"keywords": ["x"], "days_window": 7})
    settings.reset_settings()
    assert settings.get_settings() == settings.DEFAULTS


def test_effective_keywords_fallback_to_default(tmp_project):
    settings.reset_settings()
    assert settings.effective_keywords(["套保", "汇率风险"]) == ["套保", "汇率风险"]
    settings.save_settings({"keywords": ["自定义词"]})
    assert settings.effective_keywords(["套保"]) == ["自定义词"]
    settings.save_settings({"keywords": []})
    assert settings.effective_keywords(["套保"]) == ["套保"]


def test_effective_days_window(tmp_project):
    settings.reset_settings()
    assert settings.effective_days_window(180) == 180
    settings.save_settings({"days_window": 45})
    assert settings.effective_days_window(180) == 45
    settings.save_settings({"days_window": None})
    assert settings.effective_days_window(180) == 180


def test_exclude_words_clean_list(tmp_project):
    settings.save_settings({"exclude_words": [" 更正 ", "", None, "补充说明"]})
    assert settings.exclude_words() == ["更正", "补充说明"]
