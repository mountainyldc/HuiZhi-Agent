# -*- coding: utf-8 -*-
"""雷达「设置」：规则过滤词（生效词/排除词/时间窗口），持久化到 data/settings.json。
客户经理可在看板设置里修改，无需改代码；关键词为空时回退 config.yaml 默认值。"""
import json
import os

from common import project_path

DEFAULTS = {
    "keywords": [],      # 生效关键词；空 = 用 config.yaml crawl.keywords
    "exclude_words": [], # 排除词：标题命中任意一个即跳过
    "days_window": None, # 时间窗口天数；空 = 用 config.yaml crawl.days_window
}


def _path():
    return project_path("data", "settings.json")


def get_settings():
    data = {}
    if os.path.exists(_path()):
        try:
            with open(_path(), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def save_settings(patch):
    cur = get_settings()
    if isinstance(patch, dict):
        for k in DEFAULTS:
            if k in patch:
                cur[k] = patch[k]
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    return cur


def reset_settings():
    if os.path.exists(_path()):
        os.remove(_path())
    return get_settings()


def _clean_list(v):
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if x is not None and str(x).strip()]


def effective_keywords(default_keywords):
    s = get_settings()
    kws = _clean_list(s.get("keywords"))
    return kws or list(default_keywords or [])


def effective_days_window(default_days):
    s = get_settings()
    v = s.get("days_window")
    if isinstance(v, (int, float)) and v > 0:
        return int(v)
    return default_days


def exclude_words():
    return _clean_list(get_settings().get("exclude_words"))


if __name__ == "__main__":
    import sys
    if "--reset" in sys.argv:
        print(reset_settings())
    else:
        print(get_settings())
