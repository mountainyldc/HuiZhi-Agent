# -*- coding: utf-8 -*-
"""pytest 公共配置：把 engines 加入 sys.path，并提供隔离真实数据的 tmp_project 夹具。"""
import os
import shutil
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINES_DIR = os.path.join(os.path.dirname(TESTS_DIR), "engines")
if ENGINES_DIR not in sys.path:
    sys.path.insert(0, ENGINES_DIR)


@pytest.fixture
def tmp_project(monkeypatch, tmp_path):
    """把 engines 里所有 project_path 指向临时目录，读写数据全部隔离在 tmp_path。"""
    import dispatch
    import retrieve
    import rule_screen
    import settings
    import store

    for sub in ("data/crawled", "data/db", "data/queue_snapshots", "data/sample", "engines"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)

    # 广东企业名单：复制真实名单到临时目录（规则初筛需要它判定属地）
    csv_src = os.path.join(ENGINES_DIR, "region_allowlist.csv")
    shutil.copy(csv_src, str(tmp_path / "engines" / "region_allowlist.csv"))

    for mod in (store, settings, rule_screen, retrieve):
        monkeypatch.setattr(mod, "project_path", lambda *p: str(tmp_path.joinpath(*p)))
    return tmp_path
