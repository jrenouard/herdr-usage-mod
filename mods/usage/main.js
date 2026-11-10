// Subscription usage for Claude, Codex and Grok: one line per limit window.
// The numbers come from collect.py, which only reads what each CLI leaves on disk,
// so a line is as fresh as that CLI's last run (hover it to see when).
//
// Props: { demo: true | "edge" } shows made-up numbers (screenshots, checking the drawing).

import { View, div, image, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { exec, appHome, theme, layout, run, props } from "herdr";

// `color`: a full-color logo, drawn as a picture; the others take the text color.
const PROVIDERS = [
  { key: "claude", name: "Claude", icon: "icons/claude.svg", color: true },
  { key: "codex", name: "Codex", icon: "icons/codex.svg", color: true },
  { key: "grok", name: "Grok", icon: "icons/grok.svg" },
];
// macOS first: a `python3` earlier on PATH can be a broken shim, the system one isn't.
const PYTHONS = ["/usr/bin/python3", "python3"];
const REFRESH_MS = 60_000;
const WARN_AT = 80; // percent used
const RAIL_BELOW = 160; // px wide: icon and percent only
const HEADER = 41;
const ROW = 20;
const PAD = 8;

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

function span(seconds) {
  const m = Math.max(0, Math.floor(seconds / 60));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

const day = (epoch) => new Date(epoch * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

export default class Usage extends View {
  init(_props, cx) {
    this.data = null;
    this.failed = false;
    this.width = null;
    cx.timer.every(REFRESH_MS, (cx) => this.refresh(cx));
    this.refresh(cx);
  }

  async collect() {
    const demo = props()?.demo;
    const args = [`${appHome()}/mods/usage/collect.py`, ...(demo ? [demo === true ? "--demo" : `--demo=${demo}`] : [])];
    let last;
    for (const python of PYTHONS) {
      try {
        return JSON.parse((await exec(python, args, { timeout: 10_000 })).stdout);
      } catch (e) {
        last = e;
      }
    }
    throw last;
  }

  refresh(cx) {
    cx.spawn(async (cx) => {
      try {
        this.data = await this.collect();
        this.failed = false;
      } catch (e) {
        console.log("usage: collect failed", String(e));
        this.failed = true;
      }
      this.fit();
      cx.notify();
    });
  }

  // One entry per limit window; a provider with nothing on disk still gets a line.
  lines() {
    const out = [];
    for (const p of PROVIDERS) {
      const d = this.data?.[p.key];
      if (!d?.windows?.length) out.push({ p, first: true });
      else d.windows.forEach((w, i) => out.push({ p, d, w, first: i === 0 }));
    }
    return out;
  }

  // In a layout block named "usage" with a fixed height, keep that height to the lines:
  // Claude or Codex can report one window or two. Anywhere else (a docked column, a
  // pane) the size is the layout's business.
  fit() {
    const block = find(layout(), "usage");
    if (block?.content?.mod !== "usage" || block.size?.px == null) return;
    const want = HEADER + this.lines().length * ROW + PAD;
    if (block.size.px !== want) run("layout.resize", { id: "usage", px: want });
  }

  line({ p, d, w, first }, i, t, rail) {
    const now = Date.now() / 1000;
    // Past its reset time, the last reading is about a window that no longer exists.
    const stale = Boolean(w?.resets) && w.resets < now;
    const known = Boolean(w) && !stale;
    const used = known ? Math.round(w.used) : null;
    const warn = known && used >= WARN_AT;
    const seen = d?.seen ? `${span(now - d.seen)} ago` : "unknown";
    const tip = !w
      ? `${p.name}: no usage on disk yet. It shows up after ${p.name} next runs.`
      : stale
        ? `${p.name} ${w.label}: was ${Math.round(w.used)}% used, but that window reset ${day(w.resets)}. Updates when ${p.name} next runs.`
        : `${p.name} ${w.label}: ${used}% used${w.resets ? `, resets ${day(w.resets)}` : ""}. Read ${seen}.${d.note ? ` ${d.note}.` : ""}`;
    const icon = !first ? div().w(14).flex_none() : p.color ? image(p.icon).w(14).h(14).flex_none() : svg(p.icon).size(14).flex_none().text_color(t.muted);
    const percent = div().flex_none().text_color(warn ? t.blocked : known ? t.foreground : t.dim).child(known ? `${used}%` : "–");
    if (rail) return h_flex().id(`u-${i}`).h(ROW).flex_none().gap(6).items_center().justify_center().tooltip(tip).child(icon).child(percent);
    return h_flex()
      .id(`u-${i}`)
      .h(ROW)
      .flex_none()
      .px(8)
      .gap(8)
      .items_center()
      .rounded(5)
      .hover((s) => s.bg(t.hover))
      .tooltip(tip)
      .child(icon)
      .child(div().w(30).flex_none().text_color(t.dim).child(w?.label ?? ""))
      .child(
        div().flex_1().min_w(0).h(4).rounded(2).bg(t.border).overflow_hidden()
          .child(div().h(4).rounded(2).bg(warn ? t.blocked : t.accent).w(`${known ? Math.min(100, Math.max(2, used)) : 0}%`)),
      )
      .child(percent.w(32).text_right())
      .child(div().w(50).flex_none().whitespace_nowrap().text_right().text_color(t.dim).child(!w ? "" : stale ? "reset" : w.resets ? span(w.resets - now) : ""));
  }

  render() {
    const t = theme();
    const rail = this.width != null && this.width < RAIL_BELOW;
    return v_flex()
      .id("usage-root")
      .on_size_change((size, cx) => {
        if (size.width === this.width) return;
        this.width = size.width;
        cx.notify();
      })
      .size_full()
      .min_h(0)
      .bg(t.chrome)
      .border_t(1)
      .border_color(t.border)
      .text_size(11)
      .child(
        h_flex().px(16).h(HEADER).pt(14).pb(5).flex_none().items_center().justify_between()
          .when(!rail, (el) => el.child(div().text_size(11.5).font_medium().text_color(t.dim).child("Usage")))
          .when(!rail && this.failed, (el) => el.child(div().text_color(t.blocked).child("can't read"))),
      )
      .child(v_flex().px(rail ? 0 : 8).children(this.lines().map((l, i) => this.line(l, i, t, rail))));
  }
}
