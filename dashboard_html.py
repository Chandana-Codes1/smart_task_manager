"""HTML / CSS pieces for the dashboard (no Streamlit import, so they are testable).

Everything user-supplied is escaped with html.escape before it goes into HTML.
"""

from __future__ import annotations

import math
from datetime import datetime
from html import escape

import task_logic as logic

QUOTES = [
    "Small consistent tasks lead to big results.",
    "Done is better than perfect.",
    "Focus on progress, not perfection.",
    "A plan shared is a plan halfway done.",
    "Little by little, a little becomes a lot.",
    "Start where you are. Use what you have.",
]

def _flat(function):
    """Return the HTML on ONE line. Streamlit's markdown turns blank or indented
    lines inside HTML into a code block, which showed raw <text> tags."""
    import functools
    import re

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        return re.sub(r"\s*\n\s*", "", function(*args, **kwargs)).strip()

    return wrapper


PRIORITY_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}


def greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def display_name(username: str) -> str:
    return (username or "there")[:1].upper() + (username or "there")[1:]


def pending_message(stats: dict) -> str:
    pending, overdue, total = stats["pending"], stats["overdue"], stats["total"]
    if total == 0:
        return "No tasks yet. Add your first one and get started!"
    if pending == 0 and overdue == 0:
        return "You're all caught up. Great job!"
    parts = []
    if pending:
        parts.append(f"{pending} pending task{'s' if pending != 1 else ''}")
    if overdue:
        parts.append(f"{overdue} overdue")
    return "You have " + " and ".join(parts) + ". Keep going!"


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------
HERO_ART = """
<svg class="hero-art" viewBox="0 0 420 220" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#5b3a9e"/><stop offset=".55" stop-color="#d9708a"/>
      <stop offset="1" stop-color="#f6a56a"/>
    </linearGradient>
    <radialGradient id="sun" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#fff3c4"/><stop offset="1" stop-color="#ffb35c"/>
    </radialGradient>
  </defs>
  <rect width="420" height="220" fill="url(#sky)"/>
  <circle cx="300" cy="120" r="46" fill="url(#sun)" opacity=".95"/>
  <ellipse cx="120" cy="70" rx="60" ry="9" fill="#fff" opacity=".18"/>
  <ellipse cx="350" cy="48" rx="46" ry="7" fill="#fff" opacity=".16"/>
  <path d="M0 170 L70 110 L130 160 L200 95 L280 168 L340 125 L420 175 L420 220 L0 220Z" fill="#6b3f8f" opacity=".8"/>
  <path d="M0 190 L80 140 L150 185 L230 135 L310 190 L380 150 L420 185 L420 220 L0 220Z" fill="#46266b"/>
  <path d="M230 135 L330 150 L420 160 L420 220 L200 220Z" fill="#2c1750"/>
  <g fill="#1a0f33">
    <circle cx="338" cy="92" r="6"/>
    <path d="M330 100 q8 -4 14 0 l4 18 -10 6 -14 0 -6 -8z"/>
    <path d="M326 124 l22 0 0 6 -22 0z"/>
  </g>
</svg>
"""


@_flat
def hero_html(username: str, stats: dict, quote: str, now: datetime | None = None) -> str:
    return f"""
<div class="hero">
  <div class="hero-text">
    <h1>{greeting(now)}, <span>{escape(display_name(username))}</span> 👋</h1>
    <p>{escape(pending_message(stats))}</p>
    <div class="quote">“{escape(quote)}”</div>
  </div>
  {HERO_ART}
</div>"""


STAT_META = {
    "total": ("📋", "Total Tasks"),
    "completed": ("✅", "Completed"),
    "pending": ("⏳", "Pending"),
    "overdue": ("⚠️", "Overdue"),
}


@_flat
def stat_html(kind: str, value: object) -> str:
    icon, label = STAT_META[kind]
    return (
        f'<div class="stat stat-{kind}"><div class="ico">{icon}</div>'
        f'<div><div class="lbl">{label}</div><div class="num">{escape(str(value))}</div></div></div>'
    )


@_flat
def donut_html(stats: dict) -> str:
    total = stats["total"]
    r = 52
    circ = 2 * math.pi * r
    rings, offset = [], 0.0
    if total:
        for count, color in (
            (stats["completed"], "#22c55e"),
            (stats["pending"], "#8b5cf6"),
            (stats["overdue"], "#ef4444"),
        ):
            if count:
                length = circ * count / total
                rings.append(
                    f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" '
                    f'stroke-width="13" stroke-dasharray="{length:.2f} {circ - length:.2f}" '
                    f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 70 70)"/>'
                )
                offset += length
    pct = stats["completion_percentage"]
    pct_text = f"{pct:g}%"
    legend = "".join(
        f'<div class="lg"><span class="dot" style="background:{color}"></span>'
        f'<span>{name}</span><b>{stats[key]}</b></div>'
        for name, key, color in (
            ("Completed", "completed", "#22c55e"),
            ("Pending", "pending", "#8b5cf6"),
            ("Overdue", "overdue", "#ef4444"),
        )
    )
    return f"""
<div class="donut-wrap">
  <svg viewBox="0 0 140 140" class="donut" role="img" aria-label="Completion {pct_text}">
    <circle cx="70" cy="70" r="{r}" fill="none" stroke="rgba(167,139,250,.18)" stroke-width="13"/>
    {''.join(rings)}
    <text x="70" y="70" text-anchor="middle" class="d-pct">{pct_text}</text>
    <text x="70" y="90" text-anchor="middle" class="d-sub">Completion</text>
  </svg>
  <div class="legend">{legend}</div>
</div>"""


@_flat
def chips_html(task: dict) -> str:
    color = PRIORITY_COLORS.get(task.get("priority"), "#a78bfa")
    chips = [f'<span class="chip" style="color:{color};border-color:{color}55;background:{color}22">'
             f'{escape(str(task.get("priority", "")))}</span>']
    if task.get("category"):
        chips.append(f'<span class="chip c-cat">{escape(str(task["category"]))}</span>')
    due = logic.parse_due_date(task.get("due_date"))
    if due:
        state = logic.deadline_status(task)
        cls = {"overdue": "c-over", "today": "c-warn", "soon": "c-warn", "completed": "c-done"}.get(state, "c-due")
        chips.append(f'<span class="chip {cls}">📅 {due:%d %b %Y}</span>')
    if task.get("status") == "In Progress":
        chips.append('<span class="chip c-prog">In Progress</span>')
    if task.get("status") == "Completed":
        chips.append('<span class="chip c-done">✅ Done</span>')
    if task.get("shared_by"):
        chips.append(f'<span class="chip c-share">🤝 from {escape(task["shared_by"])}</span>')
    elif task.get("shared_with"):
        chips.append('<span class="chip c-share">🤝 shared</span>')
    return "".join(chips)


@_flat
def task_row_html(task: dict) -> str:
    desc = f'<div class="t-desc">{escape(task["description"])}</div>' if task.get("description") else ""
    return (
        f'<div class="t-main"><div class="t-title">{escape(task["title"])}</div>{desc}'
        f'<div class="chips">{chips_html(task)}</div></div>'
    )


@_flat
def deadline_row_html(task: dict) -> str:
    state = logic.deadline_status(task)
    color = {"overdue": "#ef4444", "today": "#f59e0b", "soon": "#f59e0b"}.get(state, "#8b5cf6")
    return (
        f'<div class="dl" style="border-left-color:{color}"><span class="dot" style="background:{color}"></span>'
        f'<span class="dl-title">{escape(task["title"])}</span>'
        f'<span class="dl-chip" style="color:{color};background:{color}22">{escape(logic.deadline_label(task))}</span></div>'
    )


@_flat
def plan_row_html(plan: dict, member_count: int, pct: float) -> str:
    return (
        f'<div class="plan"><div class="plan-ico">👥</div><div class="plan-body">'
        f'<div class="plan-name">{escape(plan["name"])}</div>'
        f'<div class="plan-sub">{member_count} member{"s" if member_count != 1 else ""} · {pct:g}% done</div>'
        f'<div class="bar"><div style="width:{max(0, min(100, pct)):g}%"></div></div></div></div>'
    )


@_flat
def cta_html() -> str:
    return (
        '<div class="cta"><div class="cta-ico">📝</div><div><div class="cta-t">Ready to get more done?</div>'
        '<div class="cta-s">Add a new task or create a collaborative plan with your friends.</div></div></div>'
    )


@_flat
def brand_html() -> str:
    return '<div class="brand"><div class="logo">✔</div><div class="brand-t">Smart Task<br>Manager</div></div>'


@_flat
def page_title_html(title: str, subtitle: str) -> str:
    return (
        f'<div class="ptitle"><div class="pt-ico">▮▮</div><div><div class="pt-t">{escape(title)}</div>'
        f'<div class="pt-s">{escape(subtitle)}</div></div></div>'
    )


def calendar_dots_css(day_state: dict[str, str], today_iso: str) -> str:
    """CSS (as text) that puts a coloured dot under calendar days that have tasks."""
    colors = {"overdue": "#ef4444", "pending": "#f59e0b", "done": "#22c55e"}
    rules = [
        f".st-key-cal_{today_iso} button{{box-shadow: inset 0 0 0 1.5px #a78bfa !important;}}"
    ]
    for iso, state in day_state.items():
        rules.append(
            f'.st-key-cal_{iso} button::after{{content:"";position:absolute;bottom:3px;left:50%;'
            f"width:5px;height:5px;margin-left:-2.5px;border-radius:50%;background:{colors[state]};}}"
        )
    return "<style>" + "".join(rules) + "</style>"


def priority_edge_css(tasks: list[dict]) -> str:
    rules = [
        f".st-key-trow_{t['task_id']}{{border-left-color:{PRIORITY_COLORS.get(t['priority'], '#8b5cf6')} !important;}}"
        for t in tasks
    ]
    return "<style>" + "".join(rules) + "</style>"


# --------------------------------------------------------------------------
# Global theme CSS
# --------------------------------------------------------------------------
SIDEBAR_ART = (
    "data:image/svg+xml;utf8,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 260' preserveAspectRatio='xMidYMax slice'%3E"
    "%3Cdefs%3E%3CradialGradient id='s'%3E%3Cstop offset='0' stop-color='%23ffd9a0'/%3E"
    "%3Cstop offset='1' stop-color='%23ff8a5c'/%3E%3C/radialGradient%3E%3C/defs%3E"
    "%3Ccircle cx='190' cy='170' r='34' fill='url(%23s)' opacity='.9'/%3E"
    "%3Cpath d='M0 200 L60 150 L120 195 L190 140 L260 190 L300 170 L300 260 L0 260Z' fill='%234a2a7a' opacity='.85'/%3E"
    "%3Cpath d='M0 225 L70 185 L140 225 L220 180 L300 220 L300 260 L0 260Z' fill='%232a1654'/%3E"
    "%3Cpath d='M20 260 L34 190 L48 260Z M44 260 L60 175 L76 260Z M250 260 L262 200 L274 260Z' fill='%23120a2b'/%3E"
    "%3C/svg%3E"
)

THEME_CSS = """
<style>
:root{--bg:#120c2b;--card:rgba(32,22,72,.78);--card2:#1c1440;--bd:rgba(139,92,246,.28);
--pri:#8b5cf6;--txt:#f3efff;--mut:#a9a0c9;}
.stApp{background:radial-gradient(1200px 600px at 78% -10%,rgba(124,58,237,.25),transparent 60%),
 radial-gradient(900px 500px at 0% 100%,rgba(236,72,153,.10),transparent 60%),#120c2b;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.4rem;max-width:1600px;}

/* sidebar */
section[data-testid="stSidebar"]{border-right:1px solid var(--bd);}
section[data-testid="stSidebar"] > div:first-child{
 background:url("__SIDEBAR_ART__") bottom/100% auto no-repeat,
 linear-gradient(180deg,#1a1040 0%,#241352 55%,#2d1760 100%);}
section[data-testid="stSidebar"] [role="radiogroup"]{gap:.15rem;}
section[data-testid="stSidebar"] label[data-baseweb="radio"]{padding:.55rem .8rem;border-radius:12px;
 width:100%;cursor:pointer;transition:background .15s, transform .15s;}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover{background:rgba(139,92,246,.18);transform:translateX(3px);}
section[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child{display:none;}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked){
 background:linear-gradient(90deg,#8b5cf6,#7c3aed);box-shadow:0 6px 18px rgba(124,58,237,.45);}
section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) *{color:#fff !important;font-weight:600;}

.brand{display:flex;align-items:center;gap:.7rem;margin:.2rem 0 1.1rem;}
.brand .logo{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;font-size:24px;
 background:linear-gradient(135deg,#a78bfa,#7c3aed);color:#fff;box-shadow:0 6px 18px rgba(124,58,237,.5);}
.brand-t{font-weight:800;font-size:1.25rem;line-height:1.1;color:#fff;}

/* top bar */
.ptitle{display:flex;align-items:center;gap:.8rem;}
.pt-ico{font-size:1.5rem;color:#a78bfa;letter-spacing:-3px;}
.pt-t{font-size:1.9rem;font-weight:800;line-height:1.05;color:#fff;}
.pt-s{color:var(--mut);font-size:.9rem;}
.st-key-topbar div[data-testid="stTextInput"] input{border-radius:999px;background:rgba(32,22,72,.8);
 border:1px solid var(--bd);padding:.65rem 1rem;}

/* cards */
[class*="st-key-card_"]{background:var(--card);border:1px solid var(--bd);border-radius:20px;
 padding:1.1rem 1.25rem;backdrop-filter:blur(6px);box-shadow:0 10px 30px rgba(8,4,24,.35);}
.card-h{font-weight:700;font-size:1.1rem;color:#fff;margin-bottom:.4rem;display:flex;align-items:center;gap:.5rem;}

/* hero */
.hero{display:flex;justify-content:space-between;overflow:hidden;border-radius:22px;min-height:170px;
 background:linear-gradient(100deg,#3a1d78 0%,#5a2b9c 48%,#a8467a 100%);border:1px solid var(--bd);
 box-shadow:0 14px 36px rgba(60,20,120,.45);}
.hero-text{padding:1.6rem 1.8rem;flex:1 1 55%;z-index:1;}
.hero h1{margin:0;font-size:2rem;font-weight:800;color:#fff;padding:0;}
.hero h1 span{color:#c4a1ff;}
.hero p{margin:.5rem 0 1rem;color:#e6dcff;font-size:1rem;}
.quote{border-left:3px solid #f472b6;padding-left:.8rem;color:#fff;font-size:.95rem;}
.hero-art{flex:0 0 46%;height:auto;max-height:230px;
 -webkit-mask-image:linear-gradient(90deg,transparent,#000 35%);mask-image:linear-gradient(90deg,transparent,#000 35%);}

/* stat cards */
.stat{display:flex;align-items:center;gap:.9rem;padding:1rem 1.1rem;border-radius:18px;border:1px solid;
 transition:transform .18s, box-shadow .18s;}
.stat .ico{width:50px;height:50px;border-radius:14px;display:grid;place-items:center;font-size:1.5rem;}
.stat .lbl{color:#d9d0f5;font-size:.9rem;}
.stat .num{font-size:1.9rem;font-weight:800;color:#fff;line-height:1.1;}
.stat-total{background:linear-gradient(135deg,#2a1d63,#1f1550);border-color:#6d54d6;}
.stat-total .ico{background:rgba(139,92,246,.3);}
.stat-completed{background:linear-gradient(135deg,#0f3b34,#12292b);border-color:#1f9d6b;}
.stat-completed .ico{background:rgba(34,197,94,.25);}
.stat-pending{background:linear-gradient(135deg,#43290f,#2c1a14);border-color:#c2790f;}
.stat-pending .ico{background:rgba(245,158,11,.25);}
.stat-overdue{background:linear-gradient(135deg,#4a1426,#2c1226);border-color:#c0334f;}
.stat-overdue .ico{background:rgba(239,68,68,.25);}
[class*="st-key-stat_"]{position:relative;}
[class*="st-key-stat_"]:hover .stat{transform:translateY(-4px);box-shadow:0 12px 26px rgba(124,58,237,.4);}
[class*="st-key-stat_"] [data-testid="stButton"]{position:absolute;inset:0;z-index:3;}
[class*="st-key-stat_"] [data-testid="stButton"] button{width:100%;height:100%;opacity:0;cursor:pointer;}

/* donut */
.donut-wrap{display:flex;align-items:center;gap:1.4rem;flex-wrap:wrap;}
.donut{width:150px;height:150px;}
.donut circle{transition:stroke-width .2s;} .donut:hover circle{stroke-width:15;}
.d-pct{fill:#fff;font-size:24px;font-weight:800;} .d-sub{fill:#bdb2e0;font-size:10px;}
.legend{display:flex;flex-direction:column;gap:.55rem;min-width:140px;flex:1;}
.lg{display:flex;align-items:center;gap:.5rem;color:#e6dcff;} .lg b{margin-left:auto;color:#fff;}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;}

/* task rows */
[class*="st-key-trow_"]{background:rgba(20,13,50,.75);border:1px solid var(--bd);border-left:4px solid #8b5cf6;
 border-radius:14px;padding:.6rem .8rem;margin-bottom:.55rem;transition:transform .15s, background .15s;}
[class*="st-key-trow_"]:hover{transform:translateX(3px);background:rgba(44,28,98,.8);}
.t-title{font-weight:700;color:#fff;font-size:1.02rem;} .t-desc{color:var(--mut);font-size:.88rem;margin:.1rem 0 .35rem;}
.chips{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.25rem;}
.chip{font-size:.78rem;padding:.12rem .6rem;border-radius:999px;border:1px solid rgba(167,139,250,.35);
 background:rgba(139,92,246,.18);color:#d8c8ff;}
.c-over{color:#ff8a9a;border-color:#ef444466;background:#ef444422;}
.c-warn{color:#ffc46b;border-color:#f59e0b66;background:#f59e0b22;}
.c-done{color:#7ee2a8;border-color:#22c55e55;background:#22c55e22;}
.c-prog{color:#8fc1ff;border-color:#3b82f666;background:#3b82f622;}
.c-share{color:#f5a8d8;border-color:#ec489966;background:#ec489922;}

/* deadlines + plans */
.dl{display:flex;align-items:center;gap:.55rem;background:rgba(20,13,50,.75);border-left:4px solid;
 border-radius:12px;padding:.6rem .8rem;margin-bottom:.45rem;}
.dl-title{font-weight:600;color:#fff;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.dl-chip{font-size:.75rem;padding:.1rem .55rem;border-radius:8px;white-space:nowrap;}
.plan{display:flex;gap:.8rem;align-items:center;}
.plan-ico{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;background:rgba(139,92,246,.25);}
.plan-body{flex:1;} .plan-name{font-weight:700;color:#fff;} .plan-sub{color:var(--mut);font-size:.85rem;}
.bar{height:6px;border-radius:6px;background:rgba(167,139,250,.2);margin-top:.35rem;overflow:hidden;}
.bar div{height:100%;background:linear-gradient(90deg,#8b5cf6,#ec4899);border-radius:6px;}

/* CTA */
[class*="st-key-cta"]{background:linear-gradient(100deg,#4a2a9a,#7c3aed 60%,#a855f7);border:1px solid var(--bd);
 border-radius:22px;padding:1.1rem 1.4rem;box-shadow:0 14px 34px rgba(124,58,237,.35);}
.cta{display:flex;gap:1rem;align-items:center;} .cta-ico{font-size:3rem;}
.cta-t{font-weight:800;font-size:1.3rem;color:#fff;} .cta-s{color:#eadfff;}

/* calendar */
.cal-title{font-weight:700;color:#fff;font-size:1.1rem;padding-top:.35rem;}
.cal-wd{display:grid;grid-template-columns:repeat(7,1fr);text-align:center;color:var(--mut);font-size:.8rem;margin:.3rem 0;}
.st-key-calwrap [data-testid="stHorizontalBlock"]{gap:.15rem;}
.st-key-calwrap [data-testid="stColumn"]{min-width:0;}
.st-key-calwrap button{position:relative;min-height:2rem;height:2.2rem;padding:0;border:none;background:transparent;
 border-radius:10px;color:#e9e2ff;transition:background .12s, transform .12s;}
.st-key-calwrap button:hover{background:rgba(139,92,246,.35);transform:scale(1.08);}
.st-key-calwrap button[kind="primary"]{background:#8b5cf6;color:#fff;font-weight:700;}
.st-key-calhead button{height:2rem;min-height:2rem;padding:0;border-radius:10px;}

/* buttons */
.stButton button{border-radius:12px;transition:transform .12s, box-shadow .12s;}
.stButton button:hover{transform:translateY(-1px);}
.stButton button[kind="primary"]{background:linear-gradient(90deg,#8b5cf6,#a855f7);border:none;color:#fff;}
/* hero quote button + CTA buttons */
.st-key-cta button{border:1.5px solid rgba(255,255,255,.85);background:rgba(255,255,255,.08);color:#fff;font-weight:600;}
.st-key-cta button[kind="primary"]{background:linear-gradient(90deg,#c084fc,#a855f7) !important;border-color:transparent;}
.st-key-topbar button{border-radius:999px;}
/* sidebar navigation buttons */
[class*="st-key-nav_"] button{justify-content:flex-start;text-align:left;border:none;border-radius:12px;
 background:transparent;color:#e9e2ff;padding:.55rem .85rem;font-weight:500;}
[class*="st-key-nav_"] button p{text-align:left;width:100%;}
[class*="st-key-nav_"] button:hover{background:rgba(139,92,246,.22);transform:translateX(3px);}
[class*="st-key-nav_"] button[kind="primary"]{background:linear-gradient(90deg,#8b5cf6,#7c3aed);color:#fff;
 font-weight:700;box-shadow:0 6px 18px rgba(124,58,237,.45);}

/* the other pages: same card look */
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px !important;border-color:var(--bd) !important;
 background:rgba(32,22,72,.62);transition:transform .15s, box-shadow .15s;}
[data-testid="stVerticalBlockBorderWrapper"]:hover{box-shadow:0 8px 22px rgba(124,58,237,.25);}
[data-testid="stForm"]{border-radius:16px;border-color:var(--bd);background:rgba(32,22,72,.55);}
[data-testid="stMetric"]{background:rgba(32,22,72,.7);border:1px solid var(--bd);border-radius:16px;padding:.8rem 1rem;}
[data-testid="stExpander"]{border-radius:14px;border-color:var(--bd);background:rgba(32,22,72,.5);}
.stMain h2{font-weight:800;}
[data-testid="stTabs"] button[aria-selected="true"]{color:#c4a1ff;}
</style>
""".replace("__SIDEBAR_ART__", SIDEBAR_ART)
