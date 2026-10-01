/* The three diagrams from "Communication Between Runners and Agents", redrawn in the Andy Smith
   design system. Each function returns an SVG string; colours come from CSS variables, so the
   same markup works in the light and the dark theme. Every node, edge, and label carries data-o,
   its place in reading order, which the presentation turns into an entrance time. */

const DIAGRAM_CSS = `
.lr-g { display: block; overflow: visible; font-variant-ligatures: none; }
.lr-g text { font-family: var(--font-text); fill: var(--fg); }
.lr-g .t { font-size: 28px; font-weight: 600; letter-spacing: -.01em; }
.lr-g .s, .lr-g .lab { font-family: var(--font-mono); font-size: 19px; fill: var(--grey); }
.lr-g .on { fill: var(--on-klein); }
.lr-g .s.on { opacity: .8; }
.lr-g .lab.hl { fill: var(--blue); }
.lr-g .lab.bad { fill: var(--red); }
.lr-g .node { fill: var(--bg); stroke: var(--fg); stroke-width: 2; }
.lr-g .node.key { fill: var(--klein); stroke: var(--klein); }
.lr-g .edge { fill: none; stroke: var(--grey); stroke-width: 2; }
.lr-g .edge.hl { stroke: var(--blue); stroke-width: 3; }
.lr-g .edge.bad { stroke: var(--red); stroke-dasharray: 9 7; }
.lr-g .edge.ctl { stroke-dasharray: 9 7; }
.lr-g .ah { fill: var(--grey); }
.lr-g .ah.hl { fill: var(--blue); }
.lr-g .ah.bad { fill: var(--red); }
`;

let DIAGRAM_ID = 0;

function diagramSvg(w, h, body) {
  const id = "lr" + ++DIAGRAM_ID;
  const marker = (c) =>
    `<marker id="${id}${c}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="16" markerHeight="16"` +
    ` markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path class="ah ${c}" d="M0,0 L10,5 L0,10 z"/></marker>`;
  return (
    `<svg class="lr-g" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><defs>` +
    marker("") + marker("hl") + marker("bad") + `</defs>` + body.replaceAll("MARK", id) + `</svg>`
  );
}

// Square node: title in Inter 600, optional sublabel in Commit Mono; `key` fills it with Klein.
function dNode(o, x, y, w, h, title, sub = "", key = false) {
  const on = key ? " on" : "";
  const ty = sub ? y + h / 2 - 4 : y + h / 2 + 10;
  return (
    `<g data-o="${o}"><rect class="node${key ? " key" : ""}" x="${x}" y="${y}" width="${w}" height="${h}"/>` +
    `<text class="t${on}" x="${x + 24}" y="${ty}">${title}</text>` +
    (sub ? `<text class="s${on}" x="${x + 24}" y="${ty + 32}">${sub}</text>` : "") +
    `</g>`
  );
}

// Edge: `cls` is "" (grey), "hl" (main path, blue 3 px), "ctl" (control, grey dashed) or "bad" (failure, red dashed).
function dEdge(o, d, cls = "", end = true, start = false) {
  const mark = cls === "ctl" ? "" : cls;
  return (
    `<path data-o="${o}" class="edge ${cls}" d="${d}"` +
    (end ? ` marker-end="url(#MARK${mark})"` : "") +
    (start ? ` marker-start="url(#MARK${mark})"` : "") +
    `/>`
  );
}

function dLabel(o, x, y, text, cls = "", anchor = "start") {
  return `<text data-o="${o}" class="lab ${cls}" x="${x}" y="${y}" text-anchor="${anchor}">${text}</text>`;
}

// 1. The simplest loop: the runner reports a result, the agent's feedback shapes the next run.
function diagramLoop() {
  return diagramSvg(
    920,
    226,
    dNode(0, 0, 0, 320, 120, "Runner", "mechanical process", true) +
      dEdge(1, "M320,60 H598", "hl") +
      dLabel(1, 459, 42, "result", "hl", "middle") +
      dNode(2, 600, 0, 320, 120, "Agent", "AI agent") +
      dEdge(3, "M760,122 V180 H160 V124") +
      dLabel(3, 460, 216, "feedback · the next run", "", "middle"),
  );
}

// 2. One message bus shared by runners, agents, and people; every edge goes both ways.
function diagramBus() {
  const xs = [0, 360, 720];
  const top = ["Runner", "Agent", "Agent"];
  let body = "";
  xs.forEach((x, i) => {
    body += dNode(i, x, 0, 240, 84, top[i]);
    body += dEdge(4 + i, `M${x + 120},88 V168`, "", true, true);
  });
  body += dNode(3, 0, 172, 960, 120, "Message bus", "Buzz · Zulip · SQLite", true);
  xs.forEach((x, i) => {
    body += dEdge(7 + i, `M${x + 120},296 V368`, "", true, true);
    body += dNode(10 + i, x, 372, 240, 84, "Person");
  });
  return diagramSvg(960, 456, body);
}

// 3. One thread per run: the runner posts its config, output, and result into the thread; the agent
//    reads every message and steers the runner; a person posts into the same thread.
function diagramThread() {
  const rows = ["Run config", "Intermediate messages", "Result", "Human message"];
  const steps = ["Config", "Execution", "Result"];
  let b = dLabel(0, 40, 112, "runner");
  steps.forEach((t, i) => {
    const y = 136 + i * 100;
    b += dNode(1 + i * 2, 40, y, 240, 64, t);
    if (i < 2) b += dEdge(2 + i * 2, `M160,${y + 66} V${y + 98}`);
  });
  b += dEdge(6, "M40,368 H14 V168 H38");
  b += dNode(7, 400, 60, 420, 56, "Thread for one run", "", true);
  rows.forEach((t, i) => {
    const y = 136 + i * 100;
    if (i < 3) b += dEdge(8 + i * 2, `M282,${y + 32} H398`, "hl");
    b += dNode(9 + i * 2, 400, y, 420, 64, t);
    b += dEdge(16, `M822,${y + 32} H900`, "", false);
  });
  b += dEdge(16, "M900,168 V468", "", false);
  b += dEdge(17, "M900,250 H1058");
  b += dLabel(17, 912, 236, "all messages");
  b += dNode(18, 1060, 200, 260, 100, "Agent", "AI agent");
  b += dEdge(19, "M1190,198 V30 H160 V134", "ctl");
  b += dLabel(19, 676, 20, "update config · stop · restart", "", "middle");
  b += dNode(20, 1060, 400, 260, 100, "Person", "steps in any time");
  b += dEdge(21, "M1190,502 V546 H610 V502");
  b += dLabel(21, 846, 534, "posts in the same thread");
  return diagramSvg(1360, 560, b);
}

const DIAGRAMS = { loop: diagramLoop, bus: diagramBus, thread: diagramThread };

function installDiagramCss() {
  const style = document.createElement("style");
  style.textContent = DIAGRAM_CSS;
  document.head.append(style);
}
