"""关键词自动扩展器 — 把少量种子词展开成几百个不重复搜索词

策略：
  1. 同义词/变体扩展（"Python" → "Python工程师", "Python开发"...）
  2. 城市组合扩展（"Python" × ["北京","上海",...] → "Python 北京"...）
  3. 经验层级扩展（"Python" → "Python 高级", "Python 实习"...）

所有扩展词都通过城市码或空格拼入搜索词，让智联每次返回不同结果集。
"""
from app.parsers.zhaopin import POPULAR_CITIES

# ── 同义词/后缀变体 ──────────────────────────────────────
_SUFFIX_VARIANTS = [
    "", "工程师", "开发", "实习", "高级", "初级",
    "全职", "兼职", "外包", "远程", "驻场",
]

# 常见技术/职位的同义词映射
_SYNONYMS = {
    "Python": ["python", "PYTHON"],
    "Java": ["java", "JAVA"],
    "C++": ["c++", "cpp", "CPlusPlus"],
    "Go": ["golang", "GO"],
    "AI": ["人工智能", "AIGC", "大模型", "机器学习"],
    "前端": ["web前端", "H5", "前台"],
    "后端": ["服务端", "server端"],
    "测试": ["QA", "测试开发", "自动化测试"],
    "运维": ["SRE", "DevOps", "运维开发"],
    "数据分析": ["数据分析师", "BI", "数据运营"],
    "产品经理": ["PM", "产品策划", "产品总监"],
    "UI设计": ["UI", "UX", "界面设计"],
    "嵌入式": ["嵌入式软件", "固件开发", "单片机"],
    "PHP": ["php"],
    "iOS": ["苹果开发", "Swift开发"],
    "Android": ["安卓开发", "安卓"],
    "算法": ["算法工程师", "NLP", "CV"],
    "网络安全": ["安全工程师", "信息安全", "渗透测试"],
    "区块链": ["web3", "智能合约"],
    "全栈": ["全栈工程师", "fullstack"],
    "DBA": ["数据库管理员", "数据库工程师"],
    "HR": ["人力资源", "招聘专员"],
    "运营": ["新媒体运营", "内容运营", "用户运营"],
    "市场": ["市场营销", "BD", "商务拓展"],
    "销售": ["销售代表", "客户经理", "大客户销售"],
    "财务": ["会计", "出纳", "审计"],
    "行政": ["行政助理", "前台", "秘书"],
    "法务": ["法律顾问", "合规"],
    "教师": ["讲师", "助教", "培训师"],
    "医生": ["医师", "临床", "护士"],
    "设计": ["平面设计", "视觉设计", "交互设计"],
    "编辑": ["文案", "记者", "自媒体"],
    "翻译": ["英语翻译", "日语翻译", "口译"],
    "厨师": ["中餐厨师", "西餐厨师", "面点师"],
    "司机": ["货运司机", "网约车司机", "叉车司机"],
    "客服": ["在线客服", "电话客服", "售后客服"],
    "物流": ["仓储", "供应链", "快递"],
    "采购": ["采购员", "招标", "供应商管理"],
    "质检": ["QC", "QA", "质量工程师"],
}


def _synonym_variants(seed):
    """基于同义词表扩展"""
    seen = {seed}
    out = [seed]
    for key, alts in _SYNONYMS.items():
        if key in seed or seed in key:
            for alt in alts:
                # 替换核心词
                candidate = seed.replace(key, alt) if key in seed else alt
                if candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
    return out


def _suffix_variants(seed):
    """后缀变体（跳过已有后缀的词）"""
    seen = {seed}
    out = [seed]
    # 如果种子已含后缀类词，不再加
    already_has_suffix = any(s in seed for s in ["工程师", "开发", "实习", "高级"])
    if already_has_suffix:
        return out
    for suf in _SUFFIX_VARIANTS:
        if not suf:
            continue
        cand = seed + suf
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def expand_keywords(seeds, include_cities=True, include_synonyms=True,
                    include_suffix=True, max_total=500):
    """把种子关键词列表展开

    Args:
        seeds: 种子关键词列表
        include_cities: 是否按城市展开（每个种子 × 主要城市）
        include_synonyms: 是否启用同义词扩展
        include_suffix: 是否启用后缀扩展
        max_total: 返回上限

    Returns:
        list[str]: 去重后的扩展关键词列表
    """
    seeds = [s.strip() for s in seeds if s.strip()]
    if not seeds:
        return []

    seen = set()
    result = []

    def add(word):
        if word in seen or not word.strip():
            return False
        seen.add(word.strip())
        result.append(word.strip())
        return len(result) >= max_total

    cities = POPULAR_CITIES if include_cities else []

    for seed in seeds:
        # 1. 基础种子
        if add(seed):
            return result

        # 2. 同义词扩展
        if include_synonyms:
            for syn in _synonym_variants(seed):
                if add(syn):
                    return result

        # 3. 后缀变体
        if include_suffix:
            for v in _suffix_variants(seed):
                if add(v):
                    return result
                # 同义词 × 后缀
                if include_synonyms:
                    for syn in _synonym_variants(seed):
                        if syn == seed:
                            continue
                        for v2 in _suffix_variants(syn):
                            if add(v2):
                                return result

        # 4. 城市组合（乘数效应最大）
        if include_cities and cities:
            bases = [seed]
            if include_synonyms:
                bases.extend(s for s in _synonym_variants(seed) if s != seed)
            if include_suffix:
                bases.extend(s for s in _suffix_variants(seed) if s != seed)
            for base in bases[:6]:  # 每个种子最多 6 个 base 变体 × 城市
                for city in cities:
                    cand = f"{base} {city}"
                    if add(cand):
                        return result

    return result


def expand_estimated_count(seeds, **kwargs):
    """估算展开后数量（不实际生成）"""
    sample = expand_keywords(seeds, max_total=10000, **kwargs)
    return len(sample)


if __name__ == "__main__":
    # 自测
    test_seeds = ["Python", "Java"]
    expanded = expand_keywords(test_seeds, max_total=500)
    print(f"种子 {test_seeds} → {len(expanded)} 个关键词")
    print("前 20:", expanded[:20])
    print("含城市的:", [k for k in expanded if any(c in k for c in POPULAR_CITIES)][:10])
