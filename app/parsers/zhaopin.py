"""智联招聘解析器 — 从 __INITIAL_STATE__ JSON 提取 + 客户端过滤"""
import json
import re
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


def _extract_initial_state(html):
    """从 HTML 中提取 __INITIAL_STATE__ JSON"""
    m = re.search(r'__INITIAL_STATE__=(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_recruiter_map(html):
    """从 HTML 提取招聘者信息 {positionNumber: (name, position)}"""
    soup = BeautifulSoup(html, "lxml")
    result = {}
    for item in soup.select(".joblist-box__item"):
        link = item.select_one(".jobinfo__name")
        if not link:
            continue
        href = link.get("href", "")
        # 从 URL 提取 positionNumber, 如 CC480422530J40785629306
        m = re.search(r'/([A-Z0-9]{10,}J\d+)\.htm', href)
        if not m:
            continue
        pos_num = m.group(1)
        staff_name_el = item.select_one(".companyinfo__staff-name")
        staff_name = staff_name_el.get_text(strip=True) if staff_name_el else ""
        # 招聘者名称格式: "姓名·职位", 如 "张先生·HRBP"
        parts = staff_name.split("·", 1) if staff_name else []
        recruiter_name = parts[0].strip() if parts else staff_name
        recruiter_position = parts[1].strip() if len(parts) > 1 else ""
        result[pos_num] = (recruiter_name, recruiter_position)
    return result


def _extract_company_tags_map(html):
    """从 HTML 提取公司标签 {positionNumber: [tags]}"""
    soup = BeautifulSoup(html, "lxml")
    result = {}
    for item in soup.select(".joblist-box__item"):
        link = item.select_one(".jobinfo__name")
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r'/([A-Z0-9]{10,}J\d+)\.htm', href)
        if not m:
            continue
        pos_num = m.group(1)
        tag_els = item.select(".companyinfo__tag .joblist-box__item-tag")
        tags = [e.get_text(strip=True) for e in tag_els]
        result[pos_num] = tags
    return result


def parse_city_district(city_val):
    """解析 '城市·区县·街道' → (city, district)"""
    parts = city_val.split("·") if city_val else []
    city_name = parts[0].strip() if parts else ""
    district = parts[1].strip() if len(parts) > 1 else ""
    return city_name, district


def parse(html, kw, city="", salary_min=0, experience="", education=""):
    """从智联招聘 HTML 提取岗位列表 + 客户端筛选

    数据源: __INITIAL_STATE__ JSON (包含完整职位详情)
    补充: HTML 选择器提取招聘者信息、公司标签
    """
    state = _extract_initial_state(html)
    if not state or "positionList" not in state:
        return []

    recruiter_map = _extract_recruiter_map(html)
    company_tags_map = _extract_company_tags_map(html)
    results = []

    for job in state["positionList"]:
        jd = job.get("jobDetailData", {}).get("position", {})
        base = jd.get("base", {})
        desc = jd.get("desc", {})
        work_loc = jd.get("workLocation", {})
        job_type = jd.get("jobType", {})

        # ── 基础信息 ──
        job_title = base.get("positionName") or job.get("name", "")
        position_number = base.get("positionNumber") or job.get("number", "")
        job_id = job.get("jobId", "")
        company_id = job.get("companyId") or job.get("companyNumber", "")
        company_name = job.get("companyName", "")

        # ── 薪资 ──
        salary_text = base.get("salary") or job.get("salary60") or ""
        salary_real = job.get("salaryReal", "")

        # ── 工作信息 ──
        work_type = base.get("workType") or job.get("workType", "")
        work_city = job.get("workCity", "")
        city_district = job.get("cityDistrict", "")
        street_name = job.get("streetName", "")
        work_address = work_loc.get("address", "")
        lat = work_loc.get("latitude", "")
        lon = work_loc.get("longitude", "")

        # ── 经验/学历 ──
        exp_val = base.get("positionWorkingExp") or job.get("workingExp", "")
        edu_val = base.get("education") or job.get("education", "")

        # ── 公司信息 ──
        industry = job.get("industryName", "")
        company_type = job.get("propertyName") or job.get("property", "")
        company_size = job.get("companySize", "")

        # ── 岗位描述 (去除 HTML 标签) ──
        raw_desc = desc.get("description", "")
        description = re.sub(r'<[^>]+>', ' ', raw_desc) if raw_desc else ""
        description = re.sub(r'\s+', ' ', description).strip()

        # ── 岗位标签 ──
        skill_labels = job.get("skillLabel") or []
        skills = ",".join(
            s.get("value", s) if isinstance(s, dict) else s
            for s in skill_labels
        ) if skill_labels else ",".join(desc.get("labels", []))

        # ── 岗位福利待遇 ──
        welfare_tags = desc.get("welfareTags") or []
        welfare_label = job.get("welfareLabel") or []
        welfare_items = []
        for w in welfare_tags + welfare_label:
            if isinstance(w, dict):
                label = w.get("label") or w.get("name") or ""
                if label:
                    welfare_items.append(label)
            elif w:
                welfare_items.append(str(w))
        welfare = ",".join(welfare_items)

        # ── 公司标签 (从 HTML) ──
        company_tags = company_tags_map.get(position_number, [])
        company_tags_str = ",".join(company_tags)

        # ── 招聘者 (从 HTML) ──
        recruiter_name, recruiter_position = recruiter_map.get(position_number, ("", ""))

        # ── 工作地区 ──
        work_area = "·".join(filter(None, [work_city, city_district, street_name]))

        # ── 行政划分 ──
        # 智联 workCity 通常为城市名, cityDistrict 为区县, streetName 为街道
        admin_level_1 = work_city      # 一级行政单位 (省/直辖市)
        admin_level_2 = city_district  # 二级行政单位 (市/区)
        admin_level_3 = street_name    # 三级行政单位 (县/街道)

        # ── 发布日期 ──
        publish_time = job.get("publishTime", "")

        # ── 职位类别 ──
        job_category_2 = job_type.get("jobTypeLevelName", "") or job.get("jobType", "")
        job_category_3 = job_type.get("subJobTypeLevelName", "") or job.get("subJobTypeLevelName", "")

        # ── 专业要求 ──
        need_major = job.get("needMajor", []) or []
        major1 = need_major[0] if len(need_major) > 0 else ""
        major2 = need_major[1] if len(need_major) > 1 else ""

        # ── URL ──
        job_url = job.get("positionUrl") or job.get("positionURL") or ""

        # ── 客户端筛选 ──
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
            # 检索参数
            "search_city": city,
            "search_job_category_2": job_category_2,
            "search_job_category_3": job_category_3,
            # 岗位基础
            "position_id": str(job_id),
            "company_id": str(company_id),
            "job_title": job_title,
            "recruiter_name": recruiter_name,
            "recruiter_position": recruiter_position,
            "work_address": work_address,
            "job_description": description,
            "company_name": company_name,
            "job_tags": skills,
            "job_welfare": welfare,
            "company_tags": company_tags_str,
            # 地区
            "work_area": work_area,
            "admin_level_1": admin_level_1,
            "admin_level_2": admin_level_2,
            "admin_level_3": admin_level_3,
            # 薪资
            "salary_text": salary_text,
            "salary_real": salary_real,
            # 要求
            "experience": exp_val,
            "education": edu_val,
            # 公司
            "industry": industry,
            "company_type": company_type,
            "company_size": company_size,
            # 地理
            "lat": str(lat),
            "lon": str(lon),
            # 其他
            "is_fulltime": work_type,
            "publish_date": publish_time,
            "major_requirement_1": major1,
            "major_requirement_2": major2,
            # 元数据
            "keyword": kw,
            "source": "zhaopin",
            "url": job_url,
        })

    return results
