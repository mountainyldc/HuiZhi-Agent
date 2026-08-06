"""公共工具：项目路径与配置加载。"""
import os

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    with open(os.path.join(PROJECT_ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_path(*parts):
    return os.path.join(PROJECT_ROOT, *parts)