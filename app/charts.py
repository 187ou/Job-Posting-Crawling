"""Plotly 图表 — 生成静态 PNG 保存到指定目录"""
import os
import plotly.express as px
from app.utils import parse_skills_count, prep_salary_df, EXPERIENCE_ORDER

LAYOUT = {
    "template": "plotly_white",
    "font": {"family": "Microsoft YaHei, SimHei, sans-serif"},
    "margin": {"l": 20, "r": 20, "t": 50, "b": 20},
    "height": 480,
}


def city_salary_fig(df):
    d = prep_salary_df(df)
    col = "admin_level_1" if "admin_level_1" in d.columns else "work_area"
    st = (
        d.groupby(col)
        .agg(a=("_salary", "mean"), c=("job_title", "count"))
        .query("c >= 2")
        .sort_values("a", ascending=False)
        .head(12)
    )
    if st.empty:
        return None
    fig = px.bar(
        st,
        x="a",
        y=st.index,
        orientation="h",
        color="a",
        color_continuous_scale="viridis",
        title="各城市平均薪资",
        labels={"a": "月薪(元)", col: "城市"},
        text=st["a"].apply(lambda x: f"{x/10000:.1f}万"),
    )
    fig.update_layout(**LAYOUT)
    return fig


def skill_fig(df):
    col = "job_tags" if "job_tags" in df.columns else "skills"
    fq = parse_skills_count(df[col]).most_common(15)
    if not fq:
        return None
    lb, vl = zip(*fq)
    fig = px.bar(
        x=list(vl),
        y=list(lb),
        orientation="h",
        title="Top 15 技能需求",
        color=list(vl),
        color_continuous_scale="blues",
        labels={"x": "次数", "y": "技能"},
    )
    fig.update_layout(**LAYOUT)
    return fig


def exp_salary_fig(df):
    d = prep_salary_df(df)
    d = d[d["experience"].isin(EXPERIENCE_ORDER)]
    ex = (
        d.groupby("experience")["_salary"]
        .mean()
        .reindex([e for e in EXPERIENCE_ORDER if e in d["experience"].values])
    )
    if ex.empty:
        return None
    fig = px.bar(
        x=ex.index,
        y=ex.values,
        title="经验 vs 薪资",
        labels={"x": "经验", "y": "月薪(元)"},
        text=[f"{v/10000:.1f}万" for v in ex.values],
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(**LAYOUT)
    return fig


def edu_pie_fig(df):
    ed = df["education"].value_counts()
    fig = px.pie(
        values=ed.values,
        names=ed.index,
        title="学历分布",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(**LAYOUT)
    return fig


def industry_fig(df):
    ind = df[df["industry"] != ""]["industry"].value_counts().head(10)
    fig = px.bar(
        x=ind.values,
        y=ind.index,
        orientation="h",
        title="行业 Top10",
        labels={"x": "岗位数", "y": "行业"},
        color=ind.values,
        color_continuous_scale="blues",
    )
    fig.update_layout(**LAYOUT)
    return fig


def salary_hist_fig(df):
    d = prep_salary_df(df)
    if d.empty:
        return None
    fig = px.histogram(
        d,
        x="_salary",
        nbins=25,
        title="薪资分布",
        labels={"_salary": "月薪(元)", "count": "岗位数"},
        color_discrete_sequence=["#58a6ff"],
    )
    fig.update_layout(**LAYOUT)
    return fig


def flowchart_fig(df=None):
    """系统架构流程图 — Plotly annotations + shapes（df参数忽略）"""
    import plotly.graph_objects as go

    # 定义节点： (x, y, 标签, 颜色)
    nodes = [
        (0.5, 1.0, "用户终端输入<br>(main.py)", "#4472C4"),
        (0.5, 0.82, "爬虫调度引擎<br>(scraper.py)", "#4472C4"),
        (0.2, 0.64, "反爬策略<br>(anti_bot.py)<br>UA轮换 · 限速 · 退避", "#ED7D31"),
        (0.8, 0.64, "HTML解析器<br>(zhaopin.py)<br>CSS选择器提取", "#ED7D31"),
        (0.5, 0.46, "薪资解析<br>(utils.py)<br>万/元/K多格式", "#A5A5A5"),
        (0.5, 0.28, "pandas 多维统计<br>城市 · 经验 · 学历 · 行业", "#70AD47"),
        (0.2, 0.10, "Plotly 图表生成<br>7类可视化图表", "#5B9BD5"),
        (0.8, 0.10, "AI 可选分析<br>OpenAI兼容接口<br>报告输出为MD", "#5B9BD5"),
    ]

    # 定义边： (起点节点索引, 终点节点索引)
    edges = [(0, 1), (1, 2), (1, 3), (2, 4), (3, 4), (4, 5), (5, 6), (5, 7)]

    fig = go.Figure()
    # 画箭头
    for src, dst in edges:
        fig.add_annotation(
            x=nodes[dst][0], y=nodes[dst][1],
            ax=nodes[src][0], ay=nodes[src][1],
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=3, arrowsize=2,
            arrowwidth=2, arrowcolor="#999999",
        )

    # 画节点
    for x, y, label, color in nodes:
        lines = label.count("<br>") + 1
        fig.add_shape(
            type="rect", x0=x-0.13, y0=y-0.04*lines, x1=x+0.13, y1=y+0.04*lines,
            line=dict(color=color, width=2), fillcolor=color, opacity=0.15,
        )
        fig.add_annotation(
            x=x, y=y, text=label, showarrow=False,
            font=dict(size=11, color="#333333"),
        )

    fig.update_layout(
        title="系统架构流程图",
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[0, 1.1]),
        template="plotly_white",
        font={"family": "Microsoft YaHei, SimHei, sans-serif"},
        width=900, height=650,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
    )
    return fig


CHART_FUNCS = [
    ("01_城市薪资对比", city_salary_fig),
    ("02_技能需求", skill_fig),
    ("03_经验vs薪资", exp_salary_fig),
    ("04_学历分布", edu_pie_fig),
    ("05_行业分布", industry_fig),
    ("06_薪资分布", salary_hist_fig),
]


def save_all_charts(df, output_dir):
    """批量生成图表 PNG 保存到 output_dir/ 目录下

    返回: [(名称, 文件路径), ...]
    """
    saved = []
    for name, func in CHART_FUNCS:
        try:
            fig = func(df)
            if fig is None:
                print(f"  [SKIP] {name}: 数据不足，跳过")
                continue
            path = os.path.join(output_dir, f"{name}.png")
            fig.write_image(path, format="png", scale=1.5)
            saved.append((name, path))
            print(f"  [OK] {name}  -> {path}")
        except Exception as e:
            print(f"  [ERR] {name}: {e}")
    return saved
