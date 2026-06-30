"""智联招聘解析器 — 显式 CSS 选择器提取 + 客户端过滤"""
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from app.utils import parse_salary

# 本地缓存已知城市码（API 查询结果会持久化到这里）
_CITY_CODE_CACHE = {
    "北京": "530", "上海": "538", "广州": "763", "深圳": "765",
    "杭州": "653", "成都": "801", "武汉": "736", "南京": "635",
    "西安": "854", "重庆": "551", "苏州": "639", "天津": "531",
    "长沙": "749", "郑州": "719", "东莞": "779", "青岛": "703",
    "合肥": "664", "佛山": "768", "宁波": "654", "昆明": "831",
    "沈阳": "599", "济南": "702", "无锡": "636", "厦门": "682",
    "福州": "681", "温州": "655", "大连": "600", "石家庄": "565",
    "哈尔滨": "622", "长春": "613", "南昌": "691", "南宁": "785",
    "贵阳": "822", "太原": "576", "兰州": "864", "乌鲁木齐": "890",
    "呼和浩特": "587", "海口": "799", "银川": "886", "西宁": "878",
}

POPULAR_CITIES = list(_CITY_CODE_CACHE.keys())


def get_city_code(city_name):
    """获取城市 jl 码，先从缓存取，再调智联 API 动态查询"""
    if not city_name or city_name == "全国":
        return ""
    if city_name in _CITY_CODE_CACHE:
        return _CITY_CODE_CACHE[city_name]
    # 动态查询 Zhaopin API
    try:
        encoded = urllib.parse.quote(city_name)
        url = f"https://fe-api.zhaopin.com/c/i/city-page/user-city?ipCity={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "JobAnalyzer/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            code = data.get("data", {}).get("code", "")
            if code:
                _CITY_CODE_CACHE[city_name] = code
                return code
    except Exception:
        pass
    return ""


def url(kw, pg, city=""):
    """构建搜索 URL，优先用 jl 城市码，无码则城市名拼入搜索词"""
    city_code = get_city_code(city) if city and city != "全国" else ""
    if city_code:
        return f"https://sou.zhaopin.com/?kw={kw}&p={pg}&jl={city_code}"
    elif city and city != "全国":
        q = f"{kw} {city}"
        return f"https://sou.zhaopin.com/?kw={urllib.parse.quote(q)}&p={pg}"
    return f"https://sou.zhaopin.com/?kw={kw}&p={pg}"


def parse(html, kw, city="", salary_min=0, experience="", education=""):
    """从智联招聘 HTML 提取岗位列表 + 客户端筛选"""
    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".joblist-box__item")
    results = []

    for item in items:
        title_el = item.select_one(".jobinfo__name")
        if not title_el:
            continue
        job_title = title_el.get_text(strip=True)

        salary_el = item.select_one(".jobinfo__salary")
        salary_text = salary_el.get_text(strip=True) if salary_el else ""

        skill_els = item.select(".jobinfo__tag .joblist-box__item-tag")
        skills = ",".join(e.get_text(strip=True) for e in skill_els)

        other_els = item.select(".jobinfo__other-info-item")
        city_val = other_els[0].get_text(strip=True) if len(other_els) > 0 else ""
        exp_val = other_els[1].get_text(strip=True) if len(other_els) > 1 else ""
        edu_val = other_els[2].get_text(strip=True) if len(other_els) > 2 else ""

        parts = city_val.split("·") if city_val else []
        city_name = parts[0] if parts else ""
        district = "·".join(parts[1:]) if len(parts) > 1 else ""

        company_el = item.select_one(".companyinfo__name")
        company_name = company_el.get_text(strip=True) if company_el else ""

        company_tag_els = item.select(".companyinfo__tag .joblist-box__item-tag")
        n = len(company_tag_els)
        industry = company_tag_els[-1].get_text(strip=True) if n >= 1 else ""
        company_size = company_tag_els[-2].get_text(strip=True) if n >= 2 else ""
        company_type = company_tag_els[-3].get_text(strip=True) if n >= 3 else ""

        if salary_min > 0:
            _, _, avg = parse_salary(salary_text)
            if avg > 0 and avg < salary_min:
                continue
        if experience and experience != "不限":
            if experience not in exp_val:
                continue
        if education and education != "不限":
            if education not in edu_val:
                continue

        results.append({
            "keyword": kw, "source": "zhaopin",
            "job_title": job_title, "salary_text": salary_text,
            "skills": skills, "city": city_name, "district": district,
            "experience": exp_val, "education": edu_val,
            "company_name": company_name, "company_type": company_type,
            "company_size": company_size, "industry": industry,
        })

    return results
