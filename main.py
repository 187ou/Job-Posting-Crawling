"""
招聘数据分析平台 - 终端交互版
运行: python main.py
"""
import sys
import os
import re
import json
import urllib.request
import getpass

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter
from app.scraper import Scraper
from app.charts import save_all_charts
from app.paths import get_output_dir, ensure_output_dirs
from app.utils import parse_salary, EXPERIENCE_ORDER

# ═══════════════════════════════════════════════
#  ANSI — 只用亮色系（90-97），避免暗色看不清
# ═══════════════════════════════════════════════
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

CYAN = "\033[96m"      # 亮青 — 标题/框线
GREEN = "\033[92m"     # 亮绿 — 成功/高薪
YELLOW = "\033[93m"    # 亮黄 — 警告/中薪
RED = "\033[91m"       # 亮红 — 错误
MAGENTA = "\033[95m"   # 亮紫 — AI/高亮
WHITE = "\033[97m"     # 亮白 — 重点文字

# 背景色组合（亮底黑字，醒目）
BANNER_BG = "\033[46m\033[30m"    # 青底黑字 — 标题栏
DONE_BG = "\033[42m\033[30m"      # 绿底黑字 — 完成
TIP_BG = "\033[47m\033[30m"       # 白底黑字 — 提示条

# ── 终端宽度 ──
try:
    COLS = os.get_terminal_size().columns
except Exception:
    COLS = 80
W = min(COLS, 72)

# ── 显示宽度计算（CJK=2, ASCII=1, ANSI码不计）──

def dlen(s):
    """字符串的终端显示宽度"""
    s = re.sub(r'\033\[[0-9;]*m', '', str(s))
    w = 0
    for ch in s:
        if '一' <= ch <= '鿿' or '　' <= ch <= '〿' or '＀' <= ch <= '￯':
            w += 2
        elif ch in '═╔╗╚╝║╭╮╰╯┌┐└┘├┤┼┬┴│─▸█░':
            w += 1
        else:
            w += 1 if ord(ch) < 256 else 2
    return w

def pad_to(s, target_w, align='<'):
    """将字符串填充到目标显示宽度"""
    cur = dlen(s)
    if cur >= target_w:
        return s
    pad = target_w - cur
    if align == '^':
        left = pad // 2
        right = pad - left
        return ' ' * left + s + ' ' * right
    elif align == '>':
        return ' ' * pad + s
    else:
        return s + ' ' * pad

def trunc_by_width(s, max_w):
    """按显示宽度截断字符串，末尾加…"""
    if dlen(s) <= max_w:
        return s
    result = ""
    for ch in s:
        if dlen(result + ch + "…") > max_w:
            return result + "…"
        result += ch
    return result

# ── 边框 ──
D = "═"
S = "─"
DL = f"{CYAN}╔{D * (W-2)}╗{RST}"
DM = f"{CYAN}║{RST}"
DR = f"{CYAN}╚{D * (W-2)}╝{RST}"

WELCOME = f"""
{DL}
{DM}{BANNER_BG}{BOLD}{pad_to('招聘数据分析平台', W-2, '^')}{RST}{DM}
{DM}{BANNER_BG}{pad_to('智联招聘 · 实时爬取 · 图表分析 · AI辅助', W-2, '^')}{RST}{DM}
{DR}
"""

SUGGESTIONS = [
    "嵌入式", "Python", "Java", "前端",
    "数据分析", "AI", "测试", "运维",
    "产品经理", "UI设计", "C++", "Go",
]
CITIES = [
    "全国", "北京", "上海", "广州", "深圳",
    "杭州", "成都", "武汉", "南京", "西安",
    "重庆", "苏州", "天津", "长沙", "郑州",
]
EXP_OPTIONS = ["不限", "应届", "1年以下", "1-3年", "3-5年", "5-10年", "10年以上"]
EDU_OPTIONS = ["不限", "高中", "大专", "本科", "硕士", "博士"]


# ═══════════════════════════════════════════════
#  输出工具
# ═══════════════════════════════════════════════

def heading(num, title):
    """大标题框"""
    text = f"Step {num}/6  {title}"
    print()
    print(f"{CYAN}{BOLD}╭{'─' * W}╮{RST}")
    print(f"{CYAN}{BOLD}│{RST} {WHITE}{BOLD}{pad_to(text, W-2, '<')}{RST}{CYAN}{BOLD}│{RST}")
    print(f"{CYAN}{BOLD}╰{'─' * W}╯{RST}")
    print()


def subheading(title):
    """小标题"""
    print(f"  {CYAN}{BOLD}▸ {title}{RST}")


def ok(msg):
    print(f"  {GREEN}{BOLD}✓{RST} {msg}")


def warn(msg):
    print(f"  {YELLOW}{BOLD}!{RST} {YELLOW}{msg}{RST}")


def err(msg):
    print(f"  {RED}{BOLD}✗{RST} {RED}{msg}{RST}")


def info(msg):
    print(f"  {DIM}{msg}{RST}")


def tip(msg):
    """提示条"""
    print(f"  {TIP_BG}{BOLD} 提示 {RST}{TIP_BG} {pad_to(msg, W-6, '<')}{RST}")


def box(items, highlight=None):
    """精致的方框"""
    max_label = max(dlen(it[0]) for it in items) if items else 10
    total_w = max_label + 36
    top = f"  {CYAN}┌{'─' * (total_w + 2)}┐{RST}"
    bot = f"  {CYAN}└{'─' * (total_w + 2)}┘{RST}"
    print(top)
    for label, value in items:
        hl = label in (highlight or [])
        color = YELLOW if hl else WHITE
        print(f"  {CYAN}│{RST}  {pad_to(label, max_label, '>')} : {color}{BOLD if hl else ''}{value}{RST}{' ' * (total_w - max_label - dlen(value) - 6)}{CYAN}│{RST}")
    print(bot)


def input_yesno(prompt, default="Y"):
    d = default.upper()
    hint = f"[{BOLD}{WHITE}{d}{RST}/n]" if d == "Y" else f"[y/{BOLD}{WHITE}{d}{RST}]"
    raw = input(f"  {prompt} {hint}: ").strip().lower()
    return (raw or default.lower()) in ("y", "yes")


# ═══════════════════════════════════════════════
#  Step 1-3: 交互配置
# ═══════════════════════════════════════════════

def step1_keyword():
    heading(1, "选择职位关键词")
    tip("支持手动输入、文件加载、或混合（文件 + 逗号分隔）")

    print(f"  {DIM}热门关键词参考：{RST}")
    for i in range(0, len(SUGGESTIONS), 6):
        tags = "    ".join(f"{WHITE}{BOLD}{k:<10}{RST}" for k in SUGGESTIONS[i:i+6])
        print(f"    {tags}")
    print()

    # 文件加载
    raw = input(f"  {WHITE}{BOLD}> 关键词文件路径 {DIM}(无则回车跳过){RST}: ").strip()
    keywords = []
    if raw:
        try:
            with open(raw, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        keywords.extend(k.strip() for k in line.replace("，", ",").split(",") if k.strip())
            ok(f"从文件加载 {len(keywords)} 个关键词")
        except Exception as e:
            err(f"读取失败: {e}")

    # 手动补充
    raw = input(f"  {WHITE}{BOLD}> 手动输入关键词 {DIM}(逗号分隔, 可回车跳过){RST}: ").strip()
    if raw:
        keywords.extend(k.strip() for k in raw.replace("，", ",").split(",") if k.strip())

    # 去重保序
    seen_kw = set()
    uniq = []
    for k in keywords:
        if k not in seen_kw:
            seen_kw.add(k)
            uniq.append(k)
    keywords = uniq

    if not keywords:
        warn("至少输入一个关键词")
        return step1_keyword()

    # ── 自动扩展 ──
    from app.keyword_expander import expand_keywords, expand_estimated_count
    if len(keywords) < 200:
        print()
        tip("关键词较少，可自动扩展以获取更多数据（同义词 + 城市组合）")
        if input_yesno(f"{WHITE}{BOLD}自动扩展关键词？{RST}", default="Y"):
            target = 300
            raw = input(f"  目标数量 {DIM}(最多500)[300]{RST}: ").strip()
            if raw:
                try: target = min(int(raw), 500)
                except ValueError: pass
            expanded = expand_keywords(keywords, max_total=target)
            ok(f"{len(keywords)} 个种子 → {len(expanded)} 个扩展关键词")
            keywords = expanded

    ok(f"共 {len(keywords)} 个不重复关键词")
    return keywords


def step2_params():
    heading(2, "设置爬取参数")
    tip("直接回车使用默认值，输入数字或文字自定义")

    # 页数 — 放开到 100（智联单关键词上限约 50 页，多关键词可跑满）
    while True:
        raw = input(f"  每关键词页数 {DIM}(每页约20条，1-100)[10]{RST}: ").strip()
        if not raw:
            pages = 10; break
        try:
            pages = int(raw)
            if 1 <= pages <= 100: break
            warn("范围: 1-100")
        except ValueError:
            warn("请输入数字")
    print()

    # 速度模式 — 决定延迟与并发
    speed_preset = {
        "1": ("极速 (delay=0.8, workers=8, 风险高)", 0.8, 8),
        "2": ("快速 (delay=1.5, workers=6, 推荐)", 1.5, 6),
        "3": ("稳健 (delay=2.5, workers=4, 默认)", 2.5, 4),
        "4": ("龟速 (delay=4.0, workers=2, 反爬严)", 4.0, 2),
    }
    print(f"  {DIM}速度预设：{RST}")
    for k, (label, _, _) in speed_preset.items():
        print(f"    {WHITE}{k}{RST} = {label}")
    raw = input(f"  选择速度 {DIM}[2=快速]{RST}: ").strip()
    if raw in speed_preset:
        _, delay, workers = speed_preset[raw]
    else:
        _, delay, workers = speed_preset["2"]
    ok(f"速度: 延迟 {delay}s, 并发 {workers}")
    print()

    subheading("可选筛选条件")
    info("(直接回车 = 不限)")

    # 城市
    cities_preview = "  ".join(f"{WHITE}{c}{RST}" for c in CITIES[:8])
    print(f"  {DIM}热门城市：{cities_preview} ...{RST}")
    city = input(f"  城市 {DIM}[全国]{RST}: ").strip() or "全国"

    # 薪资
    salary_min = 0
    raw = input(f"  最低薪资 {DIM}(万/月，如 1.5 = 1.5万)[0]{RST}: ").strip()
    if raw:
        try: salary_min = int(float(raw) * 10000)
        except ValueError: warn("格式错误，已忽略")

    # 经验 & 学历
    exp_map = {str(i): v for i, v in enumerate(EXP_OPTIONS)}
    print(f"  {DIM}经验要求：{RST}" + " | ".join(f"{WHITE}{i}{RST}={v}" for i, v in exp_map.items()))
    raw = input(f"  选择 {DIM}[0=不限]{RST}: ").strip()
    experience = exp_map.get(raw, "不限")

    edu_map = {str(i): v for i, v in enumerate(EDU_OPTIONS)}
    print(f"  {DIM}学历要求：{RST}" + " | ".join(f"{WHITE}{i}{RST}={v}" for i, v in edu_map.items()))
    raw = input(f"  选择 {DIM}[0=不限]{RST}: ").strip()
    education = edu_map.get(raw, "不限")

    return pages, city, salary_min, experience, education, delay, workers


def step3_confirm(keywords, pages, city, salary_min, experience, education, delay, workers):
    heading(3, "确认爬取配置")
    tip("请核对以下信息，无误则确认开始")

    kw_display = ", ".join(keywords[:8])
    if len(keywords) > 8:
        kw_display += f" ...+{len(keywords)-8}个"
    kw_str = f"{GREEN}{BOLD}{kw_display}{RST}"
    sal_str = f"{GREEN}{BOLD}{salary_min/10000:.1f}万/月{RST}" if salary_min > 0 else f"{DIM}不限{RST}"

    est = len(keywords) * pages * 20
    est_str = f"{YELLOW}{BOLD}~{est:,}{RST}"

    items = [
        ("关键词数", f"{WHITE}{BOLD}{len(keywords)}{RST}"),
        ("每词页数", f"{WHITE}{BOLD}{pages}{RST}"),
        ("预计条数", est_str),
        ("城市", f"{WHITE}{city}{RST}"),
        ("最低薪资", sal_str),
        ("经验要求", f"{WHITE}{experience}{RST}"),
        ("学历要求", f"{WHITE}{education}{RST}"),
        ("速度", f"{WHITE}延迟{delay}s / 并发{workers}{RST}"),
    ]
    box(items, highlight={"关键词数", "预计条数"})
    print()

    return input_yesno(f"{WHITE}{BOLD}确认开始爬取？{RST}", default="Y")


# ═══════════════════════════════════════════════
#  Step 4: 爬取
# ═══════════════════════════════════════════════

def run_scrape(keywords, pages, city, salary_min, experience, education,
               delay=1.5, workers=6, output_dir=""):
    """执行爬取。大数据量走流式，小数据量走内存。

    返回: (rows_or_none, stats, csv_path)
    """
    heading(4, "正在爬取智联招聘数据")
    tip("数据实时显示，大数据量会自动流式写盘，内存安全")

    est = len(keywords) * pages * 20
    use_stream = est > 5000  # 超过 5k 条自动流式
    csv_path = os.path.join(output_dir, "jobs.csv") if use_stream else ""

    scraper = Scraper(
        keywords=keywords, pages_per_kw=pages, delay=delay, max_workers=workers,
        city=city, salary_min=salary_min, experience=experience, education=education,
        on_log=lambda msg: info(msg),
        on_progress=lambda c, t: None,
    )

    rows, stats, csv_path = scraper.run(csv_path=csv_path if use_stream else None)

    if not stats:
        print()
        warn("未获取到数据 — 请检查网络或更换关键词")
        return None, stats, ""

    print()
    mode_hint = f" ({DIM}流式写盘 → {csv_path}{RST})" if use_stream else ""
    print(f"  {GREEN}{BOLD}✓ 爬取成功！{RST} 共获取 {GREEN}{BOLD}{stats['total']:,}{RST} 条职位数据{mode_hint}")
    return rows, stats, csv_path


# ═══════════════════════════════════════════════
#  Step 5: 统计展示
# ═══════════════════════════════════════════════

def print_stats(stats):
    if not stats: return
    heading(5, "数据统计")
    tip("以下是根据爬取结果生成的统计摘要")

    items = [
        ("职位总数", f"{GREEN}{BOLD}{stats['total']} 条{RST}"),
        ("平均薪资", f"{GREEN}{BOLD}{stats['avg_salary']:,.0f} 元/月{RST}"),
        ("最高薪资", f"{GREEN}{stats['max_salary']:,.0f} 元/月{RST}"),
        ("最低薪资", f"{stats['min_salary']:,.0f} 元/月"),
        ("覆盖城市", f"{WHITE}{stats['cities']} 个{RST}"),
        ("覆盖公司", f"{WHITE}{stats['companies']} 家{RST}"),
    ]
    box(items, highlight={"职位总数", "平均薪资"})


def _to_rows(df_or_rows):
    """统一转成 list[dict]（展示函数沿用旧接口）"""
    if isinstance(df_or_rows, list):
        return df_or_rows
    if df_or_rows is None or df_or_rows.empty:
        return []
    return df_or_rows.to_dict("records")


def print_top_jobs(rows, top_n=10):
    data = _to_rows(rows)
    if not data: return
    subheading(f"薪资排名 Top {top_n}")
    print()

    # 列宽（显示宽度）
    CW = [26, 20, 14, 8]  # 职位, 公司, 薪资, 城市

    def sort_key(r):
        return parse_salary(r.get("salary_text", ""))[2]
    top = sorted(data, key=sort_key, reverse=True)[:top_n]

    # 分隔线
    print(f"  {DIM}┌{'─' * CW[0]}┬{'─' * CW[1]}┬{'─' * CW[2]}┬{'─' * CW[3]}┐{RST}")
    print(f"  {DIM}│{RST} {pad_to('职位', CW[0]-2, '^')} {DIM}│{RST} {pad_to('公司', CW[1]-2, '^')} {DIM}│{RST} {pad_to('薪资', CW[2]-2, '^')} {DIM}│{RST} {pad_to('城市', CW[3]-2, '^')} {DIM}│{RST}")
    print(f"  {DIM}├{'─' * CW[0]}┼{'─' * CW[1]}┼{'─' * CW[2]}┼{'─' * CW[3]}┤{RST}")

    for r in top:
        job = r.get("job_title", "")
        comp = r.get("company_name", "")
        sal = r.get("salary_text", "")
        city = r.get("admin_level_1", "") or r.get("work_area", "")

        # 按显示宽度截断
        job = trunc_by_width(job, CW[0] - 2)
        comp = trunc_by_width(comp, CW[1] - 2)
        city = trunc_by_width(city, CW[3] - 2)

        avg_sal = parse_salary(sal)[2]
        if avg_sal >= 20000:
            sal_color = f"{GREEN}{BOLD}"; sal_rst = RST
        elif avg_sal >= 10000:
            sal_color = YELLOW; sal_rst = RST
        elif avg_sal > 0:
            sal_color = ""; sal_rst = ""
        else:
            sal_color = DIM; sal_rst = RST

        print(f"  {DIM}│{RST} {pad_to(job, CW[0]-2)} {DIM}│{RST} {pad_to(comp, CW[1]-2)} {DIM}│{RST} {sal_color}{pad_to(sal, CW[2]-2)}{sal_rst} {DIM}│{RST} {pad_to(city, CW[3]-2)} {DIM}│{RST}")

    print(f"  {DIM}└{'─' * CW[0]}┴{'─' * CW[1]}┴{'─' * CW[2]}┴{'─' * CW[3]}┘{RST}")


def print_city_distribution(rows):
    data = _to_rows(rows)
    if not data: return
    subheading("城市分布 Top10")
    print()

    from collections import Counter
    city_counter = Counter(r.get("admin_level_1", "未知") for r in data if r.get("admin_level_1"))
    total = sum(city_counter.values())
    bar_colors = [GREEN, CYAN, MAGENTA, YELLOW, WHITE]

    for idx, (city, count) in enumerate(city_counter.most_common(10)):
        bar_len = int(count / max(city_counter.values()) * 28)
        color = bar_colors[idx % len(bar_colors)]
        bar = f"{color}{'█' * bar_len}{RST}{DIM}{'░' * (28 - bar_len)}{RST}"
        pct = f"{count/total*100:.1f}%"
        print(f"  {WHITE}{city:<8}{RST} {bar} {BOLD}{count:>4}{RST}  {pct}")


def print_skills_top(rows, n=15):
    """技能需求 Top N"""
    data = _to_rows(rows)
    if not data: return
    subheading("技能需求 Top 15")
    print()

    skill_counter = Counter()
    for r in data:
        for tag in str(r.get("job_tags", "")).split(","):
            tag = tag.strip()
            if len(tag) >= 2:
                skill_counter[tag] += 1
    freq = skill_counter.most_common(n)
    if not freq:
        info("未提取到技能标签"); return
    max_count = freq[0][1]
    for idx, (skill, count) in enumerate(freq):
        bar_len = int(count / max_count * 30) if max_count > 0 else 0
        bar = f"{GREEN}{'█' * bar_len}{RST}{DIM}{'░' * (30 - bar_len)}{RST}"
        print(f"  {WHITE}{idx+1:>2}.{RST} {pad_to(skill, 16)} {bar} {BOLD}{count:>4}{RST}")
    print()


def print_industry_dist(rows, n=10):
    """行业分布 Top N"""
    data = _to_rows(rows)
    if not data: return
    subheading("行业分布 Top 10")
    print()
    ind_counter = Counter(r.get("industry", "") for r in data if r.get("industry"))
    if not ind_counter:
        info("未提取到行业数据"); return
    max_count = ind_counter.most_common(1)[0][1]
    colors = [CYAN, MAGENTA, YELLOW, GREEN, WHITE]
    for idx, (industry, count) in enumerate(ind_counter.most_common(n)):
        bar_len = int(count / max_count * 30) if max_count > 0 else 0
        color = colors[idx % len(colors)]
        bar = f"{color}{'█' * bar_len}{RST}{DIM}{'░' * (30 - bar_len)}{RST}"
        print(f"  {pad_to(industry, 16)} {bar} {BOLD}{count:>4}{RST}")
    print()


def print_exp_salary(rows):
    """经验-薪资对比"""
    data = _to_rows(rows)
    if not data: return
    subheading("经验 vs 平均薪资")
    print()
    exp_data = {}
    for r in data:
        exp = r.get("experience", "")
        _, _, avg = parse_salary(r.get("salary_text", ""))
        if exp and avg > 0:
            exp_data.setdefault(exp, []).append(avg)
    ordered = [(e, sum(exp_data[e]) / len(exp_data[e])) for e in EXPERIENCE_ORDER if e in exp_data]
    if not ordered:
        info("经验数据不足"); return
    max_sal = max(v for _, v in ordered)
    for exp, avg_sal in ordered:
        bar_len = int(avg_sal / max_sal * 26) if max_sal > 0 else 0
        bar = f"{GREEN}{'█' * bar_len}{RST}{DIM}{'░' * (26 - bar_len)}{RST}"
        print(f"  {pad_to(exp, 10)} {bar} {BOLD}{GREEN}{avg_sal:>8,.0f}{RST} 元/月")
    print()


def print_edu_dist(rows):
    """学历分布"""
    data = _to_rows(rows)
    if not data: return
    subheading("学历分布")
    print()
    edu_counter = Counter(r.get("education", "") for r in data if r.get("education"))
    if not edu_counter:
        info("未提取到学历数据"); return
    total = sum(edu_counter.values())
    max_count = edu_counter.most_common(1)[0][1]
    colors = [GREEN, CYAN, YELLOW, MAGENTA, WHITE]
    for idx, (edu, count) in enumerate(edu_counter.most_common(8)):
        bar_len = int(count / max_count * 28) if max_count > 0 else 0
        color = colors[idx % len(colors)]
        bar = f"{color}{'█' * bar_len}{RST}{DIM}{'░' * (28 - bar_len)}{RST}"
        pct = count / total * 100 if total > 0 else 0
        print(f"  {pad_to(edu, 8)} {bar} {BOLD}{count:>4}{RST} ({pct:.1f}%)")
    print()


# ═══════════════════════════════════════════════
#  AI 分析
# ═══════════════════════════════════════════════

def step_ai_config():
    print()
    print(f"  {CYAN}{BOLD}▸ AI 智能分析（可选）{RST}")
    tip("AI 可分析市场行情、技能趋势、薪资建议等，需自备 API Key")

    use_ai = input_yesno(f"{WHITE}{BOLD}启用 AI 分析？{RST}", default="N")
    if not use_ai:
        info("跳过 AI 分析")
        return None

    print()
    info("支持 OpenAI / DeepSeek / 硅基流动 / Ollama 等兼容接口")
    api_url = input(f"  API Base URL {DIM}(例: https://api.deepseek.com){RST}: ").strip()
    if not api_url: warn("URL 为空，跳过"); return None

    api_key = getpass.getpass(f"  API Key: ").strip()
    if not api_key: warn("Key 为空，跳过"); return None

    model = input(f"  Model {DIM}[deepseek-v4-pro]{RST}: ").strip() or "deepseek-v4-pro"
    return {"url": api_url.rstrip("/"), "key": api_key, "model": model}


def call_ai_analysis(rows, stats, api_config):
    job_summaries = []
    for r in rows[:30]:
        parts = [f"- {r.get('job_title', '')}",
                 f"  公司: {r.get('company_name', '')} | 薪资: {r.get('salary_text', '')}",
                 f"  城市: {r.get('city', '')} | 经验: {r.get('experience', '')} | 学历: {r.get('education', '')}"]
        s = r.get('skills', '')
        if s: parts.append(f"  技能: {s}")
        job_summaries.append("\n".join(parts))

    system_prompt = """你是资深招聘市场分析师，请给出专业报告。

格式：Markdown，二级标题用 ##，重要数据 **加粗**，列表用 -
每段不超过3行，中文回复，建议具体。

输出结构：
## 一、市场概况（热度、地域、公司类型）
## 二、薪资分析（区间、经验/城市对比，具体数字）
## 三、技能需求与趋势（高频技能、新方向）
## 四、求职建议（技能路径、城市策略、薪资谈判）
## 五、总结（一句话判断）"""

    user_prompt = f"""分析 {stats['total']} 条 "{rows[0].get('keyword', '')}" 职位：

统计: 均薪{stats['avg_salary']:,.0f}元/月, 最高{stats['max_salary']:,.0f}, 最低{stats['min_salary']:,.0f}, {stats['cities']}城, {stats['companies']}司

职位列表:
{chr(10).join(job_summaries)}

给出专业分析报告。"""

    base = api_config["url"].rstrip("/")
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"

    try:
        print()
        info(f"正在调用 {MAGENTA}{api_config['model']}{RST}{DIM}，等待响应...{RST}")
        req = urllib.request.Request(
            url, data=json.dumps({
                "model": api_config["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7, "max_tokens": 2048,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_config['key']}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]

    except urllib.error.HTTPError as e:
        err(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")
        return None
    except Exception as e:
        err(f"请求失败: {e}")
        return None


def print_ai_result(content):
    print()
    print(f"  {CYAN}╭{'─' * W}╮{RST}")
    print(f"  {CYAN}│{RST} {MAGENTA}{BOLD}{pad_to('AI 分析报告', W-2, '<')}{RST}{CYAN}│{RST}")
    print(f"  {CYAN}╰{'─' * W}╯{RST}")
    print()
    for line in content.split("\n"):
        s = line.strip()
        if s.startswith("## "):
            print(f"  {CYAN}{BOLD}{s}{RST}")
        elif s.startswith("### "):
            print(f"  {WHITE}{BOLD}{s}{RST}")
        elif s.startswith("- "):
            print(f"  {DIM}{s}{RST}")
        else:
            print(f"  {s}")
    print()


# ═══════════════════════════════════════════════
#  Step 6: 保存
# ═══════════════════════════════════════════════

def _rows_from_source(rows, csv_path, stats):
    """统一数据源：内存 rows 或流式 CSV → DataFrame"""
    import pandas as pd
    if rows:
        return pd.DataFrame(rows)
    if csv_path and os.path.exists(csv_path):
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    return pd.DataFrame()


def main():
    print(WELCOME)

    # Step 1-3
    keywords = step1_keyword()
    pages, city, salary_min, experience, education, delay, workers = step2_params()
    if not step3_confirm(keywords, pages, city, salary_min, experience, education, delay, workers):
        print(f"\n  {DIM}已取消，再见！{RST}\n")
        return

    # 先建输出目录（流式模式需要提前拿到路径）
    kw_str = "_".join(keywords[:3])
    if len(keywords) > 3:
        kw_str += f"_等{len(keywords)}个"
    output_dir = get_output_dir(kw_str)
    charts_dir = ensure_output_dirs(output_dir)

    # Step 4
    rows, stats, csv_path = run_scrape(
        keywords, pages, city, salary_min, experience, education,
        delay=delay, workers=workers, output_dir=output_dir,
    )
    if not stats:
        return

    # 构建 DataFrame（内存 or 读 CSV）
    import pandas as pd
    df = _rows_from_source(rows, csv_path, stats)
    if df.empty:
        warn("DataFrame 为空，跳过后续分析")
        return

    # 流式模式下 rows=None，从 df 取样本给 AI
    sample_rows = df.sample(n=min(30, len(df)), random_state=42).to_dict("records") if len(df) > 0 else []

    # AI
    ai_config = step_ai_config()
    ai_content = None
    ai_model = ""
    if ai_config:
        ai_content = call_ai_analysis(sample_rows, stats, ai_config)
        if ai_content: print_ai_result(ai_content)
        else: warn("AI 分析失败，继续后续...")
        ai_model = ai_config["model"]
        ai_config["key"] = "***"; del ai_config

    # Step 5 — 展示函数已支持 DataFrame / list[dict] 双输入
    print_stats(stats)
    print_top_jobs(df, top_n=10)
    print_city_distribution(df)
    print_skills_top(df, n=15)
    print_industry_dist(df, n=10)
    print_exp_salary(df)
    print_edu_dist(df)

    # Step 6
    heading(6, "保存数据与生成图表")
    tip("所有文件将存入 output/ 目录，方便查阅和引用")

    # 流式模式 CSV 已落盘；内存模式需要写入
    if not csv_path:
        s = Scraper(keywords)
        csv_path = s.save_csv(rows, output_dir)
    if csv_path:
        ok(f"原始数据 → {GREEN}{csv_path}{RST}")

    if ai_content:
        from datetime import datetime
        ai_path = os.path.join(output_dir, "ai_analysis.md")
        with open(ai_path, "w", encoding="utf-8") as f:
            f.write(f"# 招聘市场 AI 分析报告\n\n")
            f.write(f"| 项目 | 内容 |\n|------|------|\n")
            f.write(f"| 关键词 | {', '.join(keywords[:20])} |\n")
            f.write(f"| 生成时间 | {datetime.now():%Y-%m-%d %H:%M:%S} |\n")
            f.write(f"| 分析模型 | {ai_model} |\n")
            f.write(f"| 数据量 | {stats['total']:,} 条 |\n")
            f.write(f"| 平均薪资 | {stats['avg_salary']:,.0f} 元/月 |\n")
            f.write(f"| 薪资区间 | {stats['min_salary']:,.0f} ~ {stats['max_salary']:,.0f} 元/月 |\n")
            f.write(f"| 覆盖城市 | {stats['cities']} 个 |\n")
            f.write(f"| 覆盖公司 | {stats['companies']} 家 |\n\n---\n\n")
            f.write(ai_content.strip() + "\n")
        ok(f"AI分析报告 → {MAGENTA}{ai_path}{RST}")

    print()
    info("正在生成分析图表...")
    save_all_charts(df, charts_dir)

    # 完成
    print()
    print(f"  {DONE_BG}{BOLD}{pad_to('完成！', W, '^')}{RST}")
    print(f"  {WHITE}{BOLD}输出目录：{RST}{CYAN}{output_dir}{RST}")
    print(f"  ├── {GREEN}jobs.csv{RST}")
    if ai_content: print(f"  ├── {MAGENTA}ai_analysis.md{RST}")
    print(f"  └── {CYAN}charts/{RST}")
    for f in sorted(os.listdir(charts_dir)):
        if f.endswith(".png"):
            print(f"       ├── {f}")
    print()
    info("下次运行 python main.py 即可开始新的爬取。")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {DIM}已中断，再见！{RST}\n")
    except Exception as e:
        print(f"\n  {RED}{BOLD}✗ 发生错误：{e}{RST}")
        import traceback; traceback.print_exc()
