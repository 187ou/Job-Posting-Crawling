"""路径工具 — 项目根目录、数据目录、输出目录"""
import os
from datetime import datetime


def get_base_dir() -> str:
    """项目根目录: app/paths.py → app/ → 项目根"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir() -> str:
    """SQLite 数据库存放目录: 项目根/data"""
    d = os.path.join(get_base_dir(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def get_db_path() -> str:
    """SQLite 数据库路径"""
    return os.path.join(get_data_dir(), "jobanalyzer.db")


def get_output_dir(keyword: str) -> str:
    """根据关键词和时间戳生成输出目录: output/{keyword}_{timestamp}/

    多个关键词用下划线连接，时间戳格式 YYYYMMDD_HHMMSS
    """
    # 合并关键词为文件夹名
    safe_kw = keyword.replace(",", "_").replace("，", "_").replace(" ", "_").strip("_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dirname = f"{safe_kw}_{ts}"
    d = os.path.join(get_base_dir(), "output", dirname)
    os.makedirs(d, exist_ok=True)
    return d


def ensure_output_dirs(output_dir: str) -> str:
    """确保输出目录下的 charts/ 子目录存在，返回 charts/ 路径"""
    charts_dir = os.path.join(output_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    return charts_dir
