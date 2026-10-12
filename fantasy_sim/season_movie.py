"""The season as moving pictures (owner request, 2026-10-11): how wins and points have been banked
week by week, and how title / playoff odds have moved across the canonical runs.

Pure data preparation lives here (tested, no matplotlib import); rendering is `render_*`, which
imports matplotlib lazily so the library stays import-safe. Reads only what the season already
records -- `data/current/banked_scores.json` (the league's banked results) and the tracked
predictions log -- and invents nothing: a week with no banked result is simply not a frame.

Names are whatever the caller passes in `rename` (the CLI maps to real names for the owner's
private copy, under data/, or leaves the fictional ones for a shareable copy).
"""
import datetime as _dt

# The dataviz skill's categorical palette, DARK mode, validated against the #1a1a19 surface
# (lightness band, chroma floor, CVD separation, contrast all PASS; CVD is in the 6-8 floor band,
# so every series is also direct-labelled). Colour follows the TEAM, never its rank.
SURFACE = "#1a1a19"
TEXT = "#ffffff"
TEXT_MUTED = "#c3c2b7"
GRID = "#3a3a38"
PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]


def team_colors(teams):
    """Fixed colour per team: alphabetical order, so a team keeps its hue every week."""
    return {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(sorted(teams))}


def banked_series(banked):
    """{'weeks': [1..N], 'teams': [...], 'wins': {team: [cumulative]}, 'points': {...},
    'weekly_points': {...}} from banked_scores.json. A win is a head-to-head win or a
    beat-the-median win -- the league scores two per week."""
    weeks = sorted(int(k.split("_")[1]) for k in banked if k.startswith("week_"))
    teams = sorted({t for w in weeks for t in banked[f"week_{w}"] if not t.startswith("_")})
    wins = {t: [] for t in teams}
    points = {t: [] for t in teams}
    weekly = {t: [] for t in teams}
    for t in teams:
        w_acc = p_acc = 0.0
        for w in weeks:
            row = banked[f"week_{w}"].get(t) or {}
            w_acc += float(row.get("h2h_win") or 0) + float(row.get("median_win") or 0)
            p_acc += float(row.get("points") or 0)
            wins[t].append(w_acc)
            points[t].append(p_acc)
            weekly[t].append(float(row.get("points") or 0))
    return {"weeks": weeks, "teams": teams, "wins": wins, "points": points, "weekly_points": weekly}


def race_frames(values, steps=48, hold=100, pause=36, lead=36):
    """Bar-race frames. `values` is {team: [v_week1, v_week2, ...]}; returns a list of
    (stage_label_index, {team: (value, position)}), position 0 = top. Values interpolate
    linearly between weeks and ranks interpolate with them, so bars glide past each other.
    Paced to be read at the render fps (24): `lead` frames on week 1 first, a `steps`-frame glide
    into each next week, then `pause` frames resting on it, and `hold` frames on the last stage."""
    teams = sorted(values)
    n = len(next(iter(values.values()))) if values else 0

    def ranks(vals):
        order = sorted(teams, key=lambda t: (-vals[t], t))
        return {t: i for i, t in enumerate(order)}

    def ease(x):
        return x * x * (3 - 2 * x)

    frames = []
    for i in range(n):
        cur = {t: values[t][i] for t in teams}
        if i == 0:
            r = ranks(cur)
            frames += [(0, {t: (cur[t], float(r[t])) for t in teams})] * lead
            continue
        prev = {t: values[t][i - 1] for t in teams}
        r0, r1 = ranks(prev), ranks(cur)
        for s in range(1, steps + 1):
            f = ease(s / steps)
            frames.append((i, {t: (prev[t] + (cur[t] - prev[t]) * f,
                                   r0[t] + (r1[t] - r0[t]) * f) for t in teams}))
        frames += [frames[-1]] * pause
    if frames:
        frames += [frames[-1]] * hold
    return frames


def odds_series(rows, field):
    """[(datetime, week, {team: pct})] from the canonical, non-backfilled prediction rows in time
    order, for one season-outcome field ('Champ_Pct', 'Playoff_Pct', 'Expected_Wins'). The
    backfilled week-1 row is kept as the opening point: it is the preseason state, labelled in
    the log's own provenance."""
    out = []
    for r in sorted(rows, key=lambda r: r.get("logged_at") or ""):
        if r.get("record_type") != "week_predictions" or not r.get("canonical"):
            continue
        try:
            at = _dt.datetime.strptime(r["logged_at"], "%Y-%m-%dT%H:%M:%SZ")
        except (KeyError, ValueError, TypeError):
            continue
        vals = {o["Team"]: float(o[field]) for o in (r.get("season_outcomes") or [])
                if o.get("Team") and o.get(field) is not None}
        if vals:
            out.append((at, int(r.get("week") or 0), vals))
    return out


def renamed(d, rename):
    """{name: v} with team names mapped; unmapped names pass through."""
    return {rename.get(k, k): v for k, v in d.items()}


# ----------------------------------------------------------------------------- rendering

def _style(plt):
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "text.color": TEXT, "axes.labelcolor": TEXT_MUTED, "xtick.color": TEXT_MUTED,
        "ytick.color": TEXT_MUTED, "axes.edgecolor": GRID, "font.size": 11,
        "font.family": "DejaVu Sans",
    })


def render_race(series_values, weeks, title, unit, path, mine=None, fps=24, fmt="{:.0f}"):
    """A bar race over weeks. `series_values` {team: [cumulative per week]}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    _style(plt)
    teams = sorted(series_values)
    colors = team_colors(teams)
    frames = race_frames(series_values)
    top = max(max(v) for v in series_values.values()) or 1.0
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=100)
    fig.subplots_adjust(left=0.30, right=0.95, top=0.86, bottom=0.13)

    def draw(k):
        stage, state = frames[k]
        ax.clear()
        ax.set_xlim(0, top * 1.16)
        ax.set_ylim(len(teams) - 0.4, -0.7)
        for t in teams:
            val, pos = state[t]
            ax.barh(pos, val, height=0.74, color=colors[t], alpha=1.0 if t == mine else 0.92,
                    edgecolor=TEXT if t == mine else "none", linewidth=1.4 if t == mine else 0)
            ax.text(-top * 0.015, pos, t, ha="right", va="center",
                    color=TEXT, fontweight="bold" if t == mine else "normal")
            ax.text(val + top * 0.012, pos, fmt.format(val), ha="left", va="center", color=TEXT_MUTED)
        ax.set_yticks([])
        ax.xaxis.grid(True, color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.set_xlabel(unit)
        fig.suptitle(f"{title}  -  after week {weeks[stage]}", x=0.05, ha="left", fontsize=15,
                     fontweight="bold")

    anim = FuncAnimation(fig, draw, frames=len(frames), interval=1000 / fps)
    anim.save(path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return len(frames)


def render_odds(odds_title, odds_playoff, path, mine=None, fps=3):
    """Title % and playoff % across the canonical runs: two panels, lines drawn run by run."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.animation import FuncAnimation, PillowWriter
    _style(plt)
    n = min(len(odds_title), len(odds_playoff))
    if n < 2:
        raise ValueError("need at least two canonical prediction rows to draw a trajectory")
    teams = sorted(odds_title[0][2])
    colors = team_colors(teams)
    xs = [o[0] for o in odds_title[:n]]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4), dpi=100)
    fig.subplots_adjust(left=0.06, right=0.74, top=0.84, bottom=0.12, wspace=0.22)
    labels = []
    panels = [(axes[0], odds_title, "Title odds (%)"), (axes[1], odds_playoff, "Playoff odds (%)")]
    week_starts = {}
    for at, wk, _ in odds_title[:n]:
        week_starts.setdefault(wk, at)

    def draw(k):
        upto = min(k, n - 1) + 1
        for ax, odds, label in panels:
            ax.clear()
            ymax = max(max(o[2].values()) for o in odds[:n]) * 1.12 or 1
            ax.set_ylim(0, ymax)
            ax.set_xlim(xs[0], xs[-1] + (xs[-1] - xs[0]) * 0.02)
            for wk, at in week_starts.items():
                if wk > 0:
                    ax.axvline(at, color=GRID, linewidth=0.6)
                    ax.text(at, ymax, f" wk{wk}", color=TEXT_MUTED, fontsize=8, va="top")
            for t in teams:
                ys = [o[2].get(t) for o in odds[:upto]]
                ax.plot(xs[:upto], ys, color=colors[t], linewidth=3.2 if t == mine else 1.8,
                        zorder=3 if t == mine else 2)
                ax.plot(xs[upto - 1:upto], ys[-1:], "o", color=colors[t], markersize=6,
                        markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=4)
            ax.set_title(label, loc="left", color=TEXT_MUTED, fontsize=11)
            ax.yaxis.grid(True, color=GRID, linewidth=0.6)
            ax.set_axisbelow(True)
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=5))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        # direct labels on the right panel's edge, ordered by current value so they do not collide
        ax = axes[1]
        cur = sorted(teams, key=lambda t: -odds_playoff[upto - 1][2].get(t, 0))
        for old in labels:
            old.remove()
        del labels[:]
        for i, t in enumerate(cur):
            labels.append(fig.text(0.755, 0.80 - i * 0.075, f"{t}  {odds_playoff[upto - 1][2].get(t, 0):.0f}%",
                     color=colors[t], fontsize=9.5, fontweight="bold" if t == mine else "normal",
                     va="center"))
        fig.suptitle(f"Season odds  -  {xs[upto - 1]:%b %d}, week {odds_title[upto - 1][1]} run",
                     x=0.06, ha="left", fontsize=15, fontweight="bold")

    frames = n + 8
    anim = FuncAnimation(fig, draw, frames=frames, interval=1000 / fps)
    anim.save(path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return frames
