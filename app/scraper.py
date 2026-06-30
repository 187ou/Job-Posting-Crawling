"""爬虫 — 纯 Python 实现，无 Qt 依赖，通过回调传递进度

支持大数据量（20w+）：
  - 流式写 CSV，内存中只保留去重指纹
  - 增量统计，无需全量数据驻留内存
  - 并发与延迟可调，适配不同反爬策略
"""
import csv
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.utils import parse_salary
from app.anti_bot import RateLimiter, build_headers

SOURCE_LABEL = "智联招聘"

try:
    from curl_cffi import requests as cffi_req
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False
    import requests as std_requests

# 内部字段名（英文 key，用于代码逻辑和 dict 存储）
CSV_FIELDS = [
    "_id",
    "search_city", "search_job_category_2", "search_job_category_3",
    "position_id", "company_id", "job_title",
    "recruiter_name", "recruiter_position",
    "work_address", "job_description",
    "company_name", "job_tags", "job_welfare", "company_tags",
    "work_area", "admin_level_1", "admin_level_2", "admin_level_3",
    "salary_text", "salary_min", "salary_max", "salary_avg", "salary_real",
    "publish_date", "experience", "education",
    "industry", "company_type", "company_size",
    "lat", "lon", "is_fulltime",
    "major_requirement_1", "major_requirement_2",
    "keyword", "source", "url",
]

# 中文表头映射（写 CSV 时使用）
CSV_HEADERS_CN = {
    "_id": "序列号",
    "search_city": "检索城市",
    "search_job_category_2": "检索二级职位类别",
    "search_job_category_3": "检索三级职位类别",
    "position_id": "岗位id",
    "company_id": "公司id",
    "job_title": "岗位名",
    "recruiter_name": "招聘者名称",
    "recruiter_position": "招聘者职位",
    "work_address": "工作地址",
    "job_description": "岗位描述",
    "company_name": "公司名称",
    "job_tags": "岗位标签",
    "job_welfare": "岗位福利待遇",
    "company_tags": "公司标签",
    "work_area": "工作地区",
    "admin_level_1": "一级行政单位",
    "admin_level_2": "二级行政单位",
    "admin_level_3": "三级行政单位",
    "salary_text": "薪资文本",
    "salary_min": "最小薪资",
    "salary_max": "最大薪资",
    "salary_avg": "平均薪资",
    "salary_real": "薪资区间",
    "publish_date": "发布日期",
    "experience": "工作年限要求",
    "education": "学历要求",
    "industry": "公司行业",
    "company_type": "公司类型",
    "company_size": "公司规模",
    "lat": "岗位发布-lat",
    "lon": "岗位发布-lon",
    "is_fulltime": "是否全职",
    "major_requirement_1": "专业相关要求1",
    "major_requirement_2": "专业相关要求2",
    "keyword": "搜索关键词",
    "source": "数据来源",
    "url": "岗位链接",
}


class Scraper:
    """并发爬取智联招聘职位数据，支持流式写盘"""

    def __init__(self, keywords, pages_per_kw=5, delay=2.0, max_workers=4,
                 city="", salary_min=0, experience="", education="",
                 on_log=None, on_progress=None):
        self.keywords = keywords
        self.pages_per_kw = pages_per_kw
        self.delay = delay
        self.max_workers = min(max_workers, 12)
        self.city = city
        self.salary_min = salary_min
        self.experience = experience
        self.education = education
        self._on_log = on_log or (lambda msg: None)
        self._on_progress = on_progress or (lambda current, total: None)
        self._stop = False
        self.limiter = RateLimiter()
        self.sources = ["zhaopin"]
        # 最近一次运行产出的 CSV 路径（流式模式）
        self.last_csv_path = ""

    def stop(self):
        self._stop = True
        self._on_log("[WARN] 用户请求停止")

    def _log(self, msg):
        self._on_log(msg)

    def _prog(self, current, total):
        self._on_progress(current, total)

    def _fetch(self, url, source=None):
        headers = build_headers(source)
        if HAS_CFFI:
            return cffi_req.get(url, headers=headers, impersonate="chrome131", verify=False, timeout=25)
        return std_requests.get(url, headers=headers, timeout=25)

    def _fetch_and_parse(self, source, kw, pn, city=""):
        """返回 (items, error_msg)"""
        if self._stop:
            return [], ""
        from app.parsers.zhaopin import url as zhaopin_url, parse as zhaopin_parse
        url = zhaopin_url(kw, pn, city)
        self.limiter.wait(source, base_delay=self.delay)

        if self._stop:
            return [], "已取消"
        try:
            r = self._fetch(url, source)
            if self._stop:
                return [], "已取消"
            if r.status_code != 200:
                if r.status_code in (429, 403):
                    self.limiter.backoff(source)
                return [], f"HTTP {r.status_code}"
            self.limiter.reset_backoff(source)
        except Exception as e:
            return [], f"网络错误: {str(e)[:60]}"

        try:
            items = zhaopin_parse(r.text, kw,
                                  city=self.city, salary_min=self.salary_min,
                                  experience=self.experience, education=self.education)
        except Exception as e:
            return [], f"解析异常: {str(e)[:60]}"

        for d in items:
            d["source"] = source
        return items, ""

    # ── 流式写入 ──────────────────────────────────────────

    @staticmethod
    def _row_for_csv(d):
        """补全薪资解析字段，返回可直接写入 CSV 的 dict"""
        r = dict(d)
        mn, mx, avg = parse_salary(r.get("salary_text", ""))
        r["salary_min"] = mn
        r["salary_max"] = mx
        r["salary_avg"] = avg
        return r

    def run(self, csv_path=None, flush_every=1000):
        """执行爬取

        Args:
            csv_path: 流式写入路径。提供后数据直接落盘，内存仅保留去重指纹。
            flush_every: 每积累多少条刷盘一次。

        Returns:
            (rows_or_none, stats_dict, csv_path)
            - 未给 csv_path 时 rows_or_none 为 list[dict]（兼容旧行为）
            - 给 csv_path 时 rows_or_none 为 None（数据在磁盘）
        """
        start_t = time.time()
        tp = len(self.keywords) * len(self.sources) * self.pages_per_kw
        cp = 0
        seen = set()
        total_new = 0
        total_dup = 0
        total_err = 0

        # 增量统计量（无需全量数据）
        sal_sum = 0.0
        sal_cnt = 0
        sal_min = float("inf")
        sal_max = float("-inf")
        city_set = set()
        company_set = set()

        stream_mode = csv_path is not None
        all_rows = [] if not stream_mode else None

        if not HAS_CFFI:
            self._log("[WARN] curl_cffi 不可用，回退 requests")

        filters = []
        if self.city and self.city != "全国":
            filters.append(f"城市={self.city}")
        if self.salary_min > 0:
            filters.append(f"薪资≥{self.salary_min/10000:.0f}万")
        if self.experience and self.experience != "不限":
            filters.append(f"经验={self.experience}")
        if self.education and self.education != "不限":
            filters.append(f"学历={self.education}")
        filter_str = " | ".join(filters) if filters else "无"

        est_max = len(self.keywords) * self.pages_per_kw * 20
        self._log(f"[>>] {len(self.keywords)}关键词 x {self.pages_per_kw}页 "
                  f"[{'curl_cffi' if HAS_CFFI else 'requests'}] "
                  f"并发:{self.max_workers} 延:{self.delay:.1f}s")
        self._log(f"   筛选: {filter_str}  模式: {'流式写盘' if stream_mode else '内存'}  "
                  f"预计上限: ~{est_max:,}条")
        self._log("")

        # 打开流式文件
        csv_file = None
        csv_writer = None
        buf = []
        if stream_mode:
            csv_file = open(csv_path, "w", encoding="utf-8-sig", newline="")
            csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS,
                                        extrasaction="ignore")
            # 写中文表头
            csv_writer.writerow({f: CSV_HEADERS_CN.get(f, f) for f in CSV_FIELDS})

        def _flush():
            nonlocal buf
            if csv_writer and buf:
                csv_writer.writerows(self._row_for_csv(d) for d in buf)
                csv_file.flush()
                buf = []

        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {}
        try:
            for kw in self.keywords:
                for src in self.sources:
                    for pn in range(1, self.pages_per_kw + 1):
                        if self._stop:
                            break
                        fut = executor.submit(self._fetch_and_parse, src, kw, pn, self.city)
                        futures[fut] = (src, kw, pn)
                    if self._stop:
                        break
                if self._stop:
                    break

            for fut in as_completed(futures):
                if self._stop:
                    break
                cp += 1
                self._prog(cp, tp)
                src, kw, pn = futures[fut]
                try:
                    items, err = fut.result()
                except Exception as e:
                    total_err += 1
                    self._log(f"  [ERR] [{SOURCE_LABEL}] {kw} p{pn}: 任务崩溃 - {e}")
                    continue
                if err:
                    total_err += 1
                    self._log(f"  [WARN] [{SOURCE_LABEL}] {kw} p{pn}: {err}")
                    continue

                new = 0
                for d in items:
                    k = (d.get("job_title", ""), d.get("company_name", ""))
                    if k in seen:
                        total_dup += 1
                        continue
                    seen.add(k)
                    d["keyword"] = kw
                    d["_id"] = total_new + 1  # 行号从 1 开始
                    total_new += 1
                    new += 1

                    # 增量统计
                    s = parse_salary(d.get("salary_text", ""))
                    if s[2] > 0:
                        sal_sum += s[2]
                        sal_cnt += 1
                        if s[2] < sal_min:
                            sal_min = s[2]
                        if s[2] > sal_max:
                            sal_max = s[2]
                    c = d.get("admin_level_1", "")
                    if c:
                        city_set.add(c)
                    comp = d.get("company_name", "")
                    if comp:
                        company_set.add(comp)

                    if stream_mode:
                        buf.append(d)
                        if len(buf) >= flush_every:
                            _flush()
                    else:
                        all_rows.append(d)

                if items and (new or cp % 20 == 0):
                    elapsed = time.time() - start_t
                    rate = total_new / elapsed if elapsed > 0 else 0
                    self._log(f"  p{pn}/{self.pages_per_kw} [{SOURCE_LABEL}] {kw}: "
                              f"{len(items)}条, {new}新入 (累计{total_new:,}, "
                              f"去重{total_dup:,}, {rate:.0f}条/分)")
        finally:
            _flush()
            if csv_file:
                csv_file.close()
            if self._stop:
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

        elapsed = time.time() - start_t
        if stream_mode:
            self.last_csv_path = csv_path
            # 释放内存中的去重集（可能很大）
            seen_size = len(seen)
            seen.clear()

        if self._stop:
            self._log(f"[STOP] 已停止 | 已获取 {total_new:,} 条 | 用时 {elapsed:.0f}s")
            return (None if stream_mode else (all_rows or [])), {}, (csv_path if stream_mode else "")

        avg_sal = sal_sum / sal_cnt if sal_cnt else 0
        stats = {
            "total": total_new,
            "avg_salary": avg_sal,
            "max_salary": sal_max if sal_max != float("-inf") else 0,
            "min_salary": sal_min if sal_min != float("inf") else 0,
            "cities": len(city_set),
            "companies": len(company_set),
            "duplicates": total_dup,
            "elapsed": elapsed,
        }
        self._log(f"[DONE] 共 {total_new:,} 条 | 去重 {total_dup:,} | "
                  f"均薪 {avg_sal:,.0f} | {len(city_set)}城 {len(company_set)}司 | "
                  f"用时 {elapsed:.0f}s")
        return (None if stream_mode else (all_rows or [])), stats, (csv_path if stream_mode else "")

    # ── 兼容旧接口：一次性保存 ──────────────────────────────

    def save_csv(self, rows, output_dir):
        """保存 CSV 到指定目录（旧接口，适合小数据量）"""
        if not rows:
            return ""
        filepath = os.path.join(output_dir, "jobs.csv")
        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
                w.writerow({f: CSV_HEADERS_CN.get(f, f) for f in CSV_FIELDS})
                w.writerows(self._row_for_csv(d) for d in rows)
            self.last_csv_path = filepath
            return filepath
        except OSError as e:
            self._log(f"[WARN] CSV 写入失败: {e}")
            return ""
