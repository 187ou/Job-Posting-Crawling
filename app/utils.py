"""共享工具函数 — 薪资解析、数据预处理、常量定义"""
import re
from collections import Counter

# 标准经验排序（与智联招聘 HTML 输出一致）
EXPERIENCE_ORDER = ["应届", "1年以下", "1-3年", "3-5年", "5-10年", "10年以上"]


def parse_salary(t):
    """薪资文本 → (min, max, avg) 月薪元，失败返回 (0, 0, 0)

    支持格式: 1.2-2万/月, 8000-15000元/月, 8K-15K, 10000-20000, 面议
    """
    if not isinstance(t, str) or "面议" in t:
        return (0, 0, 0)
    t = t.strip().lower()
    if not t:
        return (0, 0, 0)

    # 1.2-2万 或 1.2-2万/月
    m = re.match(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*万", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (int(lo * 10000), int(hi * 10000), int((lo + hi) / 2 * 10000))

    # 8000-15000元 或 8000-15000元/月
    m = re.match(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*元", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (int(lo), int(hi), int((lo + hi) / 2))

    # 8K-15K, 8k-15k, 8-15K (第一个k可选)
    m = re.match(r"(\d+\.?\d*)\s*[kK]?\s*-\s*(\d+\.?\d*)\s*[kK]", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (int(lo * 1000), int(hi * 1000), int((lo + hi) / 2 * 1000))

    # 裸数字 10000-20000 (无单位)
    m = re.match(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if hi >= 1000:
            return (int(lo), int(hi), int((lo + hi) / 2))

    return (0, 0, 0)


def salary_avg(t):
    """薪资文本 → 平均月薪元，失败返回 0"""
    return parse_salary(t)[2]


def parse_skills_count(skills_series):
    """技能列 → Counter({skill: count})"""
    c = Counter()
    for s in skills_series.dropna():
        for tag in str(s).split(","):
            tag = tag.strip()
            if len(tag) >= 2:
                c[tag] += 1
    return c


def prep_salary_df(df):
    """DataFrame → 提取salary_avg列并过滤无效薪资"""
    d = df.copy()
    d["_salary"] = d["salary_text"].apply(salary_avg)
    return d[d["_salary"] > 0]
