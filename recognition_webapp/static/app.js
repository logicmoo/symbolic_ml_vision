"use strict";

const byId = (id) => document.getElementById(id);
const pageMode = document.body.dataset.page;
const canvas = byId("image-canvas");
const context = canvas.getContext("2d");
const state = {
  grid: [], palette: [], background: 0, paint: 1, result: null, selected: null,
  view: "input", revision: 0, busy: false, drawing: false, cursor: [0, 0],
  imageData: null, preview: null, editing: false,
  demoFrame: null, loadingDemo: false,
  sourcePreview: null, prevPreview: null,
  prevResult: null, prevPreview2: null, prevDebug: null, prevRef: null, prevBusy: false, twoFrame: null,
  companion: "W", overlayOpacity: 0.25, groupSort1: "consensus", groupSort2: "parts",   wEngine: "crack", strongEdgePct: 1, oldEdgePct: 25, upscale: 1, crackAngleTol: 40,
  debugPreview: null, analysisMode: "parts",
  selectedParts: new Set(),
  activeOutput: "metta", outputDrafts: new Map(),
};
let presets = [];
let demoCatalog = null;
let demoRequest = 0;
let autoAnalysisPending = false;

function error(message = "") {
  byId("error").textContent = message;
  byId("error").hidden = !message;
}

function status(message) {
  byId("status").textContent = message;
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

function setView(view) {
  state.editing = false;
  state.view = view;
  for (const name of ["prev", "input", "groups", "regions", "reconstruction"]) {
    const button = byId(`view-${name}`);
    if (!button) continue;
    const active = name === view || (name === "groups" && view === "analysis" && state.analysisMode === "groups");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  renderGrid();
  for (const button of byId("analysis-images").children) {
    button.classList.toggle("active", state.view === "analysis" && button.dataset.mode === state.analysisMode);
  }
}

function invalidate(soft = false) {
  state.revision++;
  autoAnalysisPending = false;
  state.entityMap = {};  // r# -> e# map is per-frame; the tracker repopulates it
  state.deductionFiles = [];  // cross-frame deduction files; two-frame repopulates them
  // Soft mode (frame navigation): keep every section mounted with its current content and
  // just tint it "stale" while the new frame loads; each renderer swaps its own section in
  // place and clears the tint. This avoids the whole page collapsing and reforming.
  if (soft) {
    byId("studio-content")?.classList.add("stale");
    refreshSectionNav();
    return;
  }
  byId("studio-content")?.classList.remove("stale");
  state.result = null;
  state.selected = null;
  state.preview = null;
  state.debugPreview = null;
  state.selectedParts.clear();
  state.prevPreview = null;
  state.prevResult = null;
  state.prevPreview2 = null;
  state.prevDebug = null;
  state.prevRef = null;
  // Soft mode (frame navigation): leave sections in place with their current content so
  // the page doesn't collapse and rebuild. Each renderer overwrites its own section in
  // place once the new frame's data arrives.
  if (!soft) {
    byId("prev-cell").hidden = true;
    byId("prev-companion-cell").hidden = true;
    byId("companion-cell").hidden = true;
    byId("companion-control").hidden = true;
    byId("interframe").hidden = true;
    byId("two-frame-sub").hidden = true;
    byId("tracker-sub").hidden = true;
    byId("frame-diff-sub").hidden = true;
    byId("deduction-wrap").hidden = true;
    byId("layer-images").hidden = true;
    byId("layer0-grouping").hidden = true;
    byId("layer1-grouping").hidden = true;
    byId("layer0-companion-cell").hidden = true;
    byId("layer0-parts").hidden = true;
    byId("layer1-companion-cell").hidden = true;
    byId("layer1-parts").hidden = true;
    byId("parts-grouping-panel").hidden = true;
    byId("group-tree").replaceChildren();
    byId("frame-metta").hidden = true;
    byId("frame-analysis").hidden = true;
    byId("analysis-images").replaceChildren();
    byId("object-list").replaceChildren();
    byId("object-detail").hidden = true;
    byId("empty-result").hidden = false;
    byId("json-output").textContent = "Input changed. Run recognition for a fresh result.";
    byId("artifact").replaceChildren(new Option("Run a pipeline first", ""));
    byId("artifact").disabled = true;
    byId("download-artifact").disabled = true;
    byId("pipeline-summary").hidden = true;
    byId("edit-grid").hidden = true;
    byId("view-reconstruction").textContent = "Reconstruction";
  }
  byId("download").disabled = true;
  byId("result-state").textContent = "Not run";
  for (const name of ["object-count", "shape-count", "hole-count"]) byId(name).textContent = "\u2014";
  if (pageMode === "demos" && selectedDemo()) showAnalysisStatus("Loading the selected frame...");
  status("Input ready. Recognize shapes to inspect it.");
  refreshSectionNav();
}

function loadGrid(example, note, soft = false) {
  state.grid = example.grid.map((row) => [...row]);
  state.palette = [...example.palette];
  state.background = example.background;
  state.paint = state.palette.length > 1 ? 1 : 0;
  state.cursor = [0, 0];
  state.imageData = null;
  state.demoFrame = null;
  state.sourcePreview = null;
  if (!soft) clearFrameGuide();
  invalidate(soft);
  buildPalette();
  byId("dimensions").textContent = `${state.grid[0].length} \u00d7 ${state.grid.length}`;
  byId("image-note").textContent = note;
  byId("recognize").disabled = state.busy || state.loadingDemo;
  error();
  setView("input");
}

function buildPalette() {
  const select = byId("background");
  select.replaceChildren(new Option("None (recognize every color)", "none"));
  state.palette.forEach((color, index) => select.add(new Option(`${index}: ${color}`, String(index))));
  select.value = state.background === null ? "none" : String(state.background);
  const swatches = state.palette.map((color, index) => {
    const button = document.createElement("button");
    button.className = "swatch";
    button.setAttribute("aria-label", `Paint color ${index}: ${color}`);
    button.setAttribute("aria-pressed", String(state.paint === index));
    button.classList.toggle("selected", state.paint === index);
    button.title = `${index}: ${color}`;
    const swatch = document.createElement("canvas");
    swatch.width = swatch.height = 24;
    swatch.setAttribute("aria-hidden", "true");
    const brush = swatch.getContext("2d");
    brush.fillStyle = color;
    brush.fillRect(0, 0, 24, 24);
    button.append(swatch);
    button.addEventListener("click", () => {
      state.paint = index;
      buildPalette();
      status(`Paint color ${color} selected.`);
    });
    return button;
  });
  byId("palette").replaceChildren(...swatches);
}

function renderGrid() {
  if (!state.grid.length) return;
  if (pageMode === "demos" && state.view === "prev") {
    const image = state.prevPreview;
    if (!image) {
      canvas.width = 480; canvas.height = 120;
      context.fillStyle = "#101725"; context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = "#8ea0bd"; context.font = "16px sans-serif"; context.textAlign = "center";
      context.fillText("No previous frame (this is the first frame).", canvas.width / 2, canvas.height / 2);
      byId("dimensions").textContent = "No previous frame";
      return;
    }
    const scale = Math.max(1, Math.floor(720 / Math.max(image.width, image.height)));
    canvas.width = image.width * scale; canvas.height = image.height * scale;
    context.imageSmoothingEnabled = false;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    byId("dimensions").textContent = `Previous frame ${image.width} \u00d7 ${image.height}`;
    return;
  }
  canvas.classList.toggle("original-frame", pageMode === "demos" && (state.view === "input" || !state.result));
  if (pageMode === "demos" && state.sourcePreview && (state.view === "input" || !state.result)) {
    const image = state.sourcePreview;
    const scale = Math.max(1, Math.floor(720 / Math.max(image.width, image.height)));
    canvas.width = image.width * scale;
    canvas.height = image.height * scale;
    context.imageSmoothingEnabled = false;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    byId("dimensions").textContent = `Original ${image.width} \u00d7 ${image.height}`;
    return;
  }
  if (state.result?.native && state.preview && !state.editing) {
    renderNative();
    return;
  }
  const width = state.grid[0].length;
  const height = state.grid.length;
  const cell = Math.max(8, Math.floor(720 / Math.max(width, height)));
  canvas.width = width * cell;
  canvas.height = height * cell;
  const grid = state.view === "reconstruction" && state.result ? state.result.reconstruction : state.grid;
  const selected = state.result?.objects.find((obj) => obj.id === state.selected);
  const selectedCells = new Set((selected?.cells || []).map(([x, y]) => `${x},${y}`));
  const regionColors = new Map();
  if (state.view === "regions" && state.result) {
    state.result.objects.forEach((obj, i) => {
      for (const [x, y] of obj.cells) regionColors.set(`${x},${y}`, `hsl(${(i * 137.508 + 215) % 360} 65% 66%)`);
    });
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      context.fillStyle = regionColors.get(`${x},${y}`) || state.palette[grid[y][x]];
      context.fillRect(x * cell, y * cell, cell, cell);
      if (selected && !selectedCells.has(`${x},${y}`)) {
        context.fillStyle = "#101725b0";
        context.fillRect(x * cell, y * cell, cell, cell);
      }
    }
  }
  if (byId("grid-lines").checked && cell >= 10) {
    context.strokeStyle = "#90aac529";
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x <= width; x++) { context.moveTo(x * cell, 0); context.lineTo(x * cell, canvas.height); }
    for (let y = 0; y <= height; y++) { context.moveTo(0, y * cell); context.lineTo(canvas.width, y * cell); }
    context.stroke();
  }
  if (selected) {
    context.strokeStyle = "#fff";
    context.lineWidth = Math.max(1, cell / 14);
    for (const [x, y] of selected.cells) {
      for (const [dx, dy, a, b, c, d] of [
        [0, -1, 0, 0, 1, 0], [1, 0, 1, 0, 1, 1],
        [0, 1, 1, 1, 0, 1], [-1, 0, 0, 1, 0, 0],
      ]) {
        if (selectedCells.has(`${x + dx},${y + dy}`)) continue;
        context.beginPath();
        context.moveTo((x + a) * cell, (y + b) * cell);
        context.lineTo((x + c) * cell, (y + d) * cell);
        context.stroke();
      }
    }
  }
  if (document.activeElement === canvas && state.view === "input") {
    context.strokeStyle = "#fff";
    context.lineWidth = 2;
    context.strokeRect(state.cursor[0] * cell + 2, state.cursor[1] * cell + 2, cell - 4, cell - 4);
  }
}

function renderNative() {
  const result = state.result;
  if (state.view === "analysis") {
    drawAnalysis(canvas, state.analysisMode);
    byId("dimensions").textContent = `${analysisTitle(state.analysisMode)} \u00b7 ${result.width} \u00d7 ${result.height}`;
    return;
  }
  const cell = Math.max(1, Math.floor(720 / Math.max(result.width, result.height)));
  canvas.width = result.width * cell;
  canvas.height = result.height * cell;
  byId("dimensions").textContent = `Pipeline ${result.width} \u00d7 ${result.height}`;
  context.imageSmoothingEnabled = false;
  context.drawImage(state.preview, 0, 0, canvas.width, canvas.height);
  if (state.view === "regions") {
    result.objects.forEach((obj, index) => {
      context.fillStyle = `hsl(${(index * 137.508 + 215) % 360} 65% 66%)`;
      for (const [x, y] of obj.cells) context.fillRect(x * cell, y * cell, cell, cell);
    });
  }
  if (state.view === "reconstruction" || state.selected) {
    context.fillStyle = "#10172599";
    context.fillRect(0, 0, canvas.width, canvas.height);
    for (const obj of result.objects) {
      if (state.selected && obj.id !== state.selected) continue;
      context.lineWidth = Math.max(1, cell / 3);
      for (const [paths, color] of [[obj.polygons, "#8eb1ff"], [obj.holes, "#ffab81"], [obj.midlines, "#80e3bf"]]) {
        context.strokeStyle = color;
        for (const path of paths) {
          if (!path.length) continue;
          context.beginPath();
          context.moveTo((path[0][0] + .5) * cell, (path[0][1] + .5) * cell);
          for (const [x, y] of path.slice(1)) context.lineTo((x + .5) * cell, (y + .5) * cell);
          context.stroke();
        }
      }
      context.fillStyle = "#fff3ac";
      for (const [x, y] of obj.fillpoints) {
        context.beginPath();
        context.arc((x + .5) * cell, (y + .5) * cell, Math.max(2, cell / 3), 0, Math.PI * 2);
        context.fill();
      }
    }
  }
}

function analysisTitle(mode) {
  return {
    parts: (state.result?.pipeline || byId("pipeline").value) === "opencv" ? "OpenCV parts" : "Prolog parts",
    groups: "Parts grouping", turtles: "Turtle output", debug: "Debug image",
  }[mode];
}

function showAnalysisStatus(message, failed = false) {
  if (pageMode !== "demos") return;
  byId("frame-analysis").hidden = false;
  byId("parts-grouping-panel").hidden = true;
  byId("frame-metta").hidden = true;
  byId("analysis-status").textContent = message;
  byId("analysis-status").classList.toggle("failed", failed);
  byId("analysis-images").replaceChildren(...["parts", "groups", "turtles", "debug"].map((mode) => {
    const card = document.createElement("button");
    card.className = "analysis-image pending";
    card.disabled = true;
    const title = document.createElement("strong");
    title.textContent = analysisTitle(mode);
    const placeholder = document.createElement("span");
    placeholder.className = "analysis-placeholder";
    placeholder.textContent = failed ? "Unavailable" : "Processing...";
    card.append(title, placeholder);
    return card;
  }));
}

function requestDemoAnalysis() {
  if (pageMode !== "demos" || state.loadingDemo || !state.demoFrame) return;
  autoAnalysisPending = true;
  showAnalysisStatus(state.busy ? "Queued: the latest frame will run as soon as the current request finishes." : "Starting analysis...");
  byId("result-state").textContent = state.busy ? "Queued" : "Starting";
  if (!state.busy) void recognize();
}

function turtleKinds() {
  return new Set([
    byId("turtle-outer").checked ? "outer" : null,
    byId("turtle-holes").checked ? "hole" : null,
    byId("turtle-medials").checked ? "midline" : null,
  ].filter(Boolean));
}

function visibleTurtlePrograms(result = state.result, selected = state.selectedParts) {
  if (!result?.native) return [];
  const kinds = turtleKinds();
  return result.prolog.turtle_programs.filter((program) =>
    kinds.has(program.kind) && (!selected || !selected.size || selected.has(program.region)));
}

function allLayerGroups(result = state.result) {
  return ["G", "W", "V"].flatMap((layer) => result.group_layers[layer]);
}

function displayedGroups(result = state.result) {
  return allLayerGroups(result).filter((group) => byId(`group-layer-${group.layer}`).checked);
}

function groupMemberKey(group) {
  return [...group.members].sort().join(",");
}

function groupingColors(result = state.result) {
  const colors = new Map();
  for (const group of allLayerGroups(result)) {
    const key = groupMemberKey(group);
    if (!colors.has(key)) colors.set(key, `hsl(${(colors.size * 137.508 + 150) % 360} 65% 65%)`);
  }
  return colors;
}

function colorSwatch(color) {
  const swatch = document.createElement("canvas");
  swatch.width = swatch.height = 12;
  swatch.className = "color-swatch";
  swatch.setAttribute("aria-hidden", "true");
  const brush = swatch.getContext("2d");
  brush.fillStyle = color;
  brush.fillRect(0, 0, 12, 12);
  return swatch;
}

function drawTurtle(brush, program) {
  let x = 0, y = 0, heading = 0;
  brush.strokeStyle = { outer: "#8eaeff", hole: "#ffa078", midline: "#72dcba" }[program.kind];
  brush.fillStyle = brush.strokeStyle;
  brush.lineWidth = .65;
  brush.beginPath();
  for (const command of program.commands) {
    switch (command.op) {
      case "start":
        x = command.x; y = command.y; heading = command.heading;
        brush.moveTo(x + .5, y + .5);
        break;
      case "turn":
        heading += command.degrees;
        break;
      case "forward":
        x += command.distance * Math.cos(heading * Math.PI / 180);
        y += command.distance * Math.sin(heading * Math.PI / 180);
        brush.lineTo(x + .5, y + .5);
        break;
      case "close":
        brush.closePath();
        break;
      case "dot":
        brush.fillRect(x, y, 1, 1);
        break;
      default:
        throw new Error(`Unsupported turtle drawing instruction: ${command.op}`);
    }
  }
  brush.stroke();
}

function drawAnalysis(target, mode, ctx) {
  const result = ctx?.result ?? state.result;
  const preview = ctx?.preview ?? state.preview;
  const debugPreview = ctx?.debug ?? state.debugPreview;
  const parts = ctx?.parts ?? state.selectedParts;
  const original = ctx?.original ?? state.sourcePreview;
  const overlay = ctx?.overlay === true;
  const scale = Math.max(2, Math.floor(720 / Math.max(result.width, result.height)));
  target.width = result.width * scale;
  target.height = result.height * scale;
  const brush = target.getContext("2d");
  brush.imageSmoothingEnabled = false;
  brush.fillStyle = "#101725";
  brush.fillRect(0, 0, target.width, target.height);
  brush.scale(scale, scale);
  const regionParts = result.opencv ? result.opencv.parts : result.prolog.parts;
  function paintPart(part, color) {
    brush.fillStyle = color;
    if (part.pixelRuns) {
      for (const [y, left, right] of part.pixelRuns) brush.fillRect(left, y, right - left + 1, 1);
    } else {
      for (const [x, y] of part.cells) brush.fillRect(x, y, 1, 1);
    }
  }
  if (mode === "debug") {
    brush.drawImage(debugPreview, 0, 0, result.width, result.height);
  } else if (mode === "turtles") {
    for (const program of visibleTurtlePrograms(result, parts)) drawTurtle(brush, program);
  } else if (mode === "parts") {
    regionParts.forEach((part, index) => paintPart(part, `hsl(${(index * 137.508 + 215) % 360} 65% 65%)`));
  } else if (mode === "groups") {
    const groups = ctx?.groupsOverride ?? displayedGroups(result);
    const colors = groupingColors(result);
    if (parts && parts.size) {
      brush.drawImage(preview, 0, 0, result.width, result.height);
      brush.fillStyle = "#101725cc";
      brush.fillRect(0, 0, result.width, result.height);
      const partColors = new Map();
      for (const group of [...groups].reverse()) {
        for (const member of group.members) partColors.set(member, colors.get(groupMemberKey(group)));
      }
      for (const part of regionParts) if (parts.has(part.id)) paintPart(part, partColors.get(part.id) || part.color);
    } else {
      for (const group of [...groups].reverse()) {
        for (const part of regionParts) if (group.members.includes(part.id)) paintPart(part, colors.get(groupMemberKey(group)));
      }
    }
  }
  if (original && overlay && state.overlayOpacity > 0) {
    brush.globalAlpha = state.overlayOpacity;
    brush.drawImage(original, 0, 0, result.width, result.height);
    brush.globalAlpha = 1;
  }
}

function renderFrameAnalysis() {
  if (pageMode !== "demos" || !state.result?.native) return;
  const result = state.result;
  byId("frame-analysis").hidden = false;
  byId("analysis-status").classList.remove("failed");
  byId("analysis-status").textContent = result.object_count
    ? `${state.demoFrame?.label || "Frame"} \u00b7 frame ${state.demoFrame?.frameId || "0"} \u00b7 ${result.object_count} foreground regions`
    : `Frame ${state.demoFrame?.frameId || "0"} has no detected foreground. An empty original or grouping image can be a valid baseline.`;
  const selCount = state.selectedParts.size;
  const thumbnails = [
    { key: "V", title: "V groups", mode: "groups", ctx: { groupsOverride: result.group_layers.V, parts: new Set() },
      caption: `${result.group_layers.V.length} visual (V) groups` },
    { key: "W", title: "W groups", mode: "groups", ctx: { groupsOverride: result.group_layers.W, parts: new Set() },
      caption: `${result.group_layers.W.length} working (W) groups` },
    { key: "selection", title: "Selected parts", mode: "groups", ctx: { parts: state.selectedParts },
      caption: selCount ? `${selCount} selected parts` : "no parts selected \u00b7 all groups" },
    { key: "turtles", title: "Turtle (selected)", mode: "turtles", ctx: { parts: state.selectedParts },
      caption: `${visibleTurtlePrograms().length} / ${result.prolog.turtle_programs.length} programs \u00b7 ${selCount ? "selected parts" : "all parts"}` },
  ];
  byId("analysis-images").replaceChildren(...thumbnails.map((thumb) => {
    const button = document.createElement("button");
    button.className = "analysis-image";
    button.dataset.mode = thumb.key;
    button.classList.toggle("companion-selected", state.companion === thumb.key);
    button.setAttribute("aria-label", `Use ${thumb.title} as the companion image`);
    button.setAttribute("aria-pressed", String(state.companion === thumb.key));
    const title = document.createElement("strong");
    title.textContent = thumb.title;
    const image = document.createElement("canvas");
    image.setAttribute("aria-hidden", "true");
    drawAnalysis(image, thumb.mode, { overlay: true, ...thumb.ctx });
    attachHover(image, () => state.result);
    const caption = document.createElement("small");
    caption.textContent = thumb.caption;
    button.append(title, image, caption);
    button.addEventListener("click", () => setCompanion(state.companion === thumb.key ? "none" : thumb.key));
    return button;
  }));
  renderPartsGrouping();
  byId("companion-control").hidden = false;
  renderCompanion();
}

function setCompanion(mode) {
  state.companion = mode;
  for (const control of document.querySelectorAll(".companion-button")) {
    const on = control.dataset.companion === mode;
    control.classList.toggle("active", on);
    control.setAttribute("aria-pressed", String(on));
  }
  for (const thumb of byId("analysis-images").children) {
    const on = thumb.dataset.mode === mode;
    thumb.classList.toggle("companion-selected", on);
    thumb.setAttribute("aria-pressed", String(on));
  }
  byId("group-preview").classList.toggle("companion-selected", mode === "selection");
  byId("companion-status").textContent = mode === "none"
    ? "Click an image above to show it as the companion beside the frame."
    : `Companion beside the frame: ${analysisTitle(mode)}.`;
  renderCompanion();
  renderPrevPair();
  void ensurePrevPipeline();
}

function refreshPartSelection() {
  renderFrameAnalysis();
  if (state.view === "analysis") renderGrid();
}

function renderPartsGrouping() {
  if (pageMode !== "demos" || !state.result?.native) return;
  const result = state.result;
  const tree = byId("group-tree");
  const open = new Set([...tree.querySelectorAll("details[open]")].map((node) => node.dataset.group));
  const firstRender = tree.children.length === 0;
  const parts = new Map(result.prolog.parts.map((part) => [part.id, part]));
  const layerGroups = displayedGroups();
  const memberIds = new Set(layerGroups.flatMap((group) => group.members));
  const colors = groupingColors();
  const childParent = new Map((result.prolog.child_of || []).map(([child, parent]) => [child, parent]));
  const parentChildren = new Map();
  for (const [child, parent] of (result.prolog.child_of || [])) {
    if (!parentChildren.has(parent)) parentChildren.set(parent, []);
    parentChildren.get(parent).push(child);
  }
  for (const layer of ["G", "W", "V"]) byId(`group-count-${layer}`).textContent = `(${result.group_layers[layer].length})`;
  const merged = new Map();
  for (const group of layerGroups) {
    const key = groupMemberKey(group);
    if (!merged.has(key)) {
      merged.set(key, { id: key, key, members: group.members, area: group.area, layers: [], byLayer: {}, other: false });
    }
    const node = merged.get(key);
    if (!node.layers.includes(group.layer)) node.layers.push(group.layer);
    node.byLayer[group.layer] = group;
  }
  const allNodes = [...merged.values()];
  const layerRank = (node) => Math.min(...node.layers.map((l) => ["G", "W", "V"].indexOf(l)));
  const compareBy = (key, a, b) => {
    if (key === "parts") return b.members.length - a.members.length;
    if (key === "area") return b.area - a.area;
    if (key === "layer") return layerRank(a) - layerRank(b);
    return b.layers.length - a.layers.length;
  };
  const groups = [...allNodes].sort((a, b) =>
    compareBy(state.groupSort1, a, b) || compareBy(state.groupSort2, a, b) || b.members.length - a.members.length);
  const other = [...parts.keys()].filter((id) => !memberIds.has(id));
  if (other.length) groups.push({ id: "other-parts", members: other, other: true });
  const makeNode = (group, index) => {
    const details = document.createElement("details");
    details.dataset.group = group.id;
    details.open = open.has(group.id) || (firstRender && index === 0);
    const summary = document.createElement("summary");
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.group = group.id;
    const selected = group.members.filter((id) => state.selectedParts.has(id)).length;
    checkbox.checked = selected === group.members.length;
    checkbox.indeterminate = selected > 0 && selected < group.members.length;
    checkbox.setAttribute("aria-label", `Select parts in ${group.other ? "other parts" : (group.layers || []).join("+")}`);
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", () => {
      for (const id of group.members) {
        if (checkbox.checked) state.selectedParts.add(id);
        else state.selectedParts.delete(id);
      }
      refreshPartSelection();
    });
    const text = document.createElement("span");
    const layerOrder = { W: 0, G: 1, V: 2 };
    const orderedLayers = [...(group.layers || [])].sort((a, b) => (layerOrder[a] ?? 9) - (layerOrder[b] ?? 9));
    text.textContent = group.other ? `Other parts (${group.members.length})`
      : `${orderedLayers.map((layer) => group.byLayer[layer].id).join(" + ")} \u00b7 ${group.members.length} ${group.members.length === 1 ? "part" : "parts"} \u00b7 ${group.area} px`;
    label.append(checkbox, colorSwatch(group.other ? "#8b9db4" : colors.get(group.key)), text);
    summary.append(label);
    summary.addEventListener("mouseenter", () => highlightGroupMembers(group.members));
    summary.addEventListener("mouseleave", clearHighlight);
    details.append(summary);
    if (!group.other) {
      if (group.layers.length > 1) {
        const idLine = document.createElement("p");
        idLine.className = "group-advisory";
        idLine.textContent = "Exact consensus across layers.";
        details.append(idLine);
      }
      const g = group.byLayer.G;
      if (g) {
        const reason = document.createElement("p");
        reason.className = "group-advisory";
        reason.textContent = `G accepted: ${g.reason.replaceAll("_", " ")}.`;
        details.append(reason);
      }
      if (group.byLayer.V) {
        const note = document.createElement("p");
        note.className = "group-advisory";
        note.textContent = "V visual proposal (advisory).";
        details.append(note);
      }
      const kids = [...new Set(group.members.flatMap((id) => parentChildren.get(id) || []))];
      if (kids.length) {
        const boxNote = document.createElement("p");
        boxNote.className = "group-advisory child-note";
        boxNote.textContent = `\u25a3 Square box containing ${kids.length} child glyph${kids.length === 1 ? "" : "s"}: ${kids.sort().join(", ")}.`;
        details.append(boxNote);
      }
      const parentsOf = [...new Set(group.members.map((id) => childParent.get(id)).filter(Boolean))];
      const allChildren = group.members.every((id) => childParent.has(id));
      if (allChildren && parentsOf.length === 1 && !group.members.includes(parentsOf[0])) {
        const childNote = document.createElement("p");
        childNote.className = "group-advisory child-note";
        childNote.textContent = `\u21b3 Child glyph group inside box ${parentsOf[0]}.`;
        details.append(childNote);
      }
    }
    if (group.byLayer?.W && result.opencv) {
      const members = [...group.members].sort().join(",");
      const matching = result.opencv.visualGroups.filter((candidate) => [...candidate.members].sort().join(",") === members);
      if (matching.length) {
        const note = document.createElement("p");
        note.className = "group-advisory";
        note.textContent = `OpenCV ${matching.map((item) => item.id).join(", ")} matches these members (advisory).`;
        details.append(note);
      }
    }
    for (const id of group.members) {
      const part = parts.get(id);
      const memberLabel = document.createElement("label");
      memberLabel.className = "group-member";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.part = id;
      input.checked = state.selectedParts.has(id);
      input.setAttribute("aria-label", `Select part ${id}`);
      input.addEventListener("change", () => {
        if (input.checked) state.selectedParts.add(id);
        else state.selectedParts.delete(id);
        refreshPartSelection();
      });
      // Show the stable identity (e#) when the tracker has bound this region; keep the
      // per-frame OpenCV r# only as a hover title so identities stay consistent everywhere.
      const eid = state.entityMap?.[id];
      const shown = eid || id;
      memberLabel.title = eid ? `${eid} (region ${id})` : id;
      memberLabel.append(input, colorSwatch(part.color), document.createTextNode(`${shown} \u00b7 ${part.color} \u00b7 ${part.area} px`));
      memberLabel.addEventListener("mouseenter", () => highlightGroupMembers([id]));
      memberLabel.addEventListener("mouseleave", clearHighlight);
      details.append(memberLabel);
    }
    return details;
  };
  const built = groups.map((group, index) => [group, makeNode(group, index)]);
  const elByGroup = new Map(built.map(([group, el]) => [group, el]));
  const memberSets = new Map(built.map(([group]) => [group, new Set(group.members)]));
  const nestable = built.map(([group]) => group).filter((group) => !group.other);
  const isStrictSubset = (a, b) => a.members.length < b.members.length && a.members.every((id) => memberSets.get(b).has(id));
  const topLevel = [];
  const childCount = new Map();
  for (const [group, el] of built) {
    let parent = null;
    if (!group.other) {
      for (const candidate of nestable) {
        if (candidate !== group && isStrictSubset(group, candidate) &&
            (!parent || candidate.members.length < parent.members.length)) parent = candidate;
      }
    }
    if (parent && elByGroup.has(parent)) {
      el.classList.add("nested-node");
      elByGroup.get(parent).append(el);
      childCount.set(parent, (childCount.get(parent) || 0) + 1);
    } else {
      topLevel.push(el);
    }
  }
  for (const [group, el] of built) {
    const n = childCount.get(group);
    if (!n) continue;
    const badge = document.createElement("span");
    badge.className = "nested-count";
    badge.textContent = `\u2325 ${n} nested`;
    el.querySelector("summary").append(badge);
  }
  tree.replaceChildren(...topLevel);
  byId("parts-grouping-panel").hidden = false;
  byId("clear-parts").disabled = state.selectedParts.size === 0;
  byId("select-all-parts").disabled = state.selectedParts.size === parts.size;
  byId("part-selection-status").textContent = state.selectedParts.size
    ? `${state.selectedParts.size} parts selected. Turtle draws only those parts.`
    : "No parts selected: turtle draws all parts.";
  drawAnalysis(byId("group-preview"), "groups", { overlay: true });
}

byId("group-sort1")?.addEventListener("change", (event) => { state.groupSort1 = event.target.value; renderPartsGrouping(); });
byId("group-sort2")?.addEventListener("change", (event) => { state.groupSort2 = event.target.value; renderPartsGrouping(); });
byId("clear-parts").addEventListener("click", () => {
  state.selectedParts.clear();
  refreshPartSelection();
});
byId("select-all-parts").addEventListener("click", () => {
  if (state.result?.native) state.selectedParts = new Set(state.result.prolog.parts.map((part) => part.id));
  refreshPartSelection();
});
for (const layer of ["G", "W", "V"]) {
  byId(`group-layer-${layer}`).addEventListener("change", onLayerChange);
}

function onLayerChange() {
  const checked = ["G", "W", "V"].filter((layer) => byId(`group-layer-${layer}`).checked);
  if (checked.length === 1 && state.result?.native) {
    const members = state.result.group_layers[checked[0]].flatMap((group) => group.members);
    state.selectedParts = new Set(members);
  }
  refreshPartSelection();
}

function redrawLayerCompanions() {
  // Re-render the layer companion canvases from cached layer results (e.g. after the
  // turtle outer/inner/medials toggles change what the turtle companion draws).
  for (const prefix of ["layer0", "layer1"]) {
    const result = state[`${prefix}Result`];
    const cell = byId(`${prefix}-companion-cell`);
    if (!cell || !result) continue;
    const mode = state.companion;
    if (mode === "none" || mode === "original") {
      cell.hidden = true;
      continue;
    }
    const label = prefix === "layer0" ? "Layer 0" : "Layer 1";
    const ok = companionDraw(byId(`${prefix}-companion-canvas`), mode,
      { result, preview: state[`${prefix}Preview`], debug: state[`${prefix}Debug`],
        parts: null, original: state[`${prefix}Source`], overlay: true }, true);
    cell.hidden = !ok;
    if (ok) byId(`${prefix}-companion-tag`).textContent = `${label} companion: ${COMPANION_LABELS[mode]}`;
  }
}

for (const id of ["turtle-outer", "turtle-holes", "turtle-medials"]) {
  byId(id).addEventListener("change", () => {
    renderFrameAnalysis();
    if (state.view === "analysis" && state.analysisMode === "turtles") renderGrid();
    // Turtle programs must know which layers to draw EVERYWHERE they render:
    // the frame companion, the previous-frame companion, and the layer companions.
    renderCompanion();
    renderPrevPair();
    redrawLayerCompanions();
  });
}

function thumbnail(obj) {
  const mini = document.createElement("canvas");
  mini.width = mini.height = 80;
  mini.setAttribute("aria-hidden", "true");
  const brush = mini.getContext("2d");
  const cells = obj.canonical_cells;
  const width = Math.max(...cells.map(([x]) => x)) + 1;
  const height = Math.max(...cells.map(([, y]) => y)) + 1;
  const size = 56 / Math.max(width, height);
  brush.fillStyle = obj.color;
  for (const [x, y] of cells) brush.fillRect((80 - width * size) / 2 + x * size, (80 - height * size) / 2 + y * size, size, size);
  return mini;
}

function selectObject(identifier) {
  if (pageMode === "demos") {
    if (state.selectedParts.has(identifier)) state.selectedParts.delete(identifier);
    else state.selectedParts.add(identifier);
    refreshPartSelection();
    return;
  }
  state.selected = state.selected === identifier ? null : identifier;
  const obj = state.result.objects.find((item) => item.id === state.selected);
  for (const button of byId("object-list").children) {
    const selected = button.dataset.id === state.selected;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  const detail = byId("object-detail");
  detail.hidden = !obj;
  detail.replaceChildren();
  if (obj) {
    const heading = document.createElement("h3");
    heading.textContent = "Observed geometry";
    detail.append(heading);
    const [x, y, width, height] = obj.bounds;
    for (const [label, value] of [
      ["Region", obj.id], ["Color", obj.color], ["Position", `(${x}, ${y})`],
      ["Extent", `${width} \u00d7 ${height}`], ["Filled cells", obj.area],
      ["Enclosed holes", obj.hole_count], ["Touching regions", obj.adjacent_to.join(", ") || "None"],
      ["Shape identity", obj.shape_id],
    ]) {
      const row = document.createElement("div");
      row.className = "detail-row";
      for (const text of [label, value]) {
        const span = document.createElement("span");
        span.textContent = String(text);
        row.append(span);
      }
      detail.append(row);
    }
    const note = document.createElement("p");
    note.className = "detail-note";
    const count = state.result.objects.filter((item) => item.shape_id === obj.shape_id).length;
    note.textContent = count > 1 ? `${count} regions share this normalized shape. That is a geometry match, not proof that they are the same object.` : "One occurrence of this normalized shape in this image.";
    detail.append(note);
  }
  renderGrid();
}

function showResult(result) {
  state.result = result;
  state.selected = null;
  byId("object-count").textContent = result.object_count;
  byId("shape-count").textContent = result.shape_count;
  byId("hole-count").textContent = result.objects.reduce((sum, obj) => sum + obj.hole_count, 0);
  byId("empty-result").hidden = result.object_count > 0;
  byId("object-detail").hidden = true;
  byId("result-state").textContent = "Current";
  byId("download").disabled = false;
  byId("json-output").textContent = JSON.stringify(result, null, 2);
  byId("object-list").replaceChildren(...result.objects.map((obj) => {
    const button = document.createElement("button");
    button.className = "object-card";
    button.dataset.id = obj.id;
    button.setAttribute("aria-pressed", "false");
    button.append(thumbnail(obj));
    const text = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = obj.name.replaceAll("_", " ");
    const info = document.createElement("small");
    info.textContent = `${obj.area} cells \u00b7 ${obj.geometry.replaceAll("_", " ")}`;
    text.append(name, info);
    button.append(text);
    button.addEventListener("click", () => selectObject(obj.id));
    return button;
  }));
  if (result.native) {
    const validParts = new Set(result.prolog.parts.map((part) => part.id));
    state.selectedParts = new Set([...state.selectedParts].filter((id) => validParts.has(id)));
    byId("frame-metta").hidden = false;
    byId("frame-metta-title").textContent = `AtomSpace \u00b7 frame ${result.frame.frameId}`;
    renderOutputEditor();
    byId("dimensions").textContent = `${result.width} \u00d7 ${result.height}`;
    const sourceLabel = state.demoFrame ? `${state.demoFrame.label} / frame ${state.demoFrame.frameId}` : result.source.kind === "original_image" ? "Original image bytes" : "Edited grid";
    byId("image-note").textContent = `${sourceLabel} \u2192 ${result.pipeline === "opencv" ? "OpenCV" : "Prolog shape finder"} \u2192 Prolog groups and turtles. Contours are approximate.`;
    byId("edit-grid").hidden = false;
    byId("view-reconstruction").textContent = "Contours";
    const summary = byId("pipeline-summary");
    summary.replaceChildren();
    summary.hidden = false;
    for (const stage of result.stages) {
      const line = document.createElement("strong");
      line.textContent = `${stage.engine} ${stage.version}: executed`;
      summary.append(line);
    }
    for (const message of [`${result.prolog.groups.length} Prolog groups \u00b7 ${result.milliseconds} ms`, ...result.warnings]) {
      const paragraph = document.createElement("p");
      paragraph.textContent = message;
      summary.append(paragraph);
    }
    byId("artifact").replaceChildren(...result.artifacts.map((item, index) => new Option(item.name, String(index))));
    byId("artifact").disabled = false;
    byId("download-artifact").disabled = false;
    status(`${result.stages.map((stage) => stage.engine).join(" + ")} executed. ${result.object_count} foreground regions; ${result.prolog.groups.length} Prolog groups. No files or directories written.`);
  } else {
    status(result.object_count === 0
      ? "No foreground regions. Draw a shape or change the background selection."
      : `${result.object_count} regions recognized. Reconstruction matches the analysis grid exactly.`);
    byId("frame-metta").hidden = false;
    byId("frame-metta-title").textContent = "AtomSpace output";
    renderOutputEditor();
  }
  renderFrameAnalysis();
  renderGrid();
  renderPrevPair();
  void renderTwoFrame();
  void renderTracker();
  void renderFrameDiff();
  refreshSectionNav();
  byId("studio-content")?.classList.remove("stale");
}

async function recognize(forceEvent) {
  if (state.busy || state.loadingDemo || !state.grid.length) return;
  // A real click on Run again passes the event: bypass the disk cache for a live run.
  const forceLive = Boolean(forceEvent);
  autoAnalysisPending = false;
  const revision = state.revision;
  state.busy = true;
  byId("recognize").disabled = true;
  byId("download").disabled = true;
  byId("download-artifact").disabled = true;
  byId("result-state").textContent = "Running";
  error();
  const pipeline = byId("pipeline").value;
  showAnalysisStatus(`Running ${pipeline === "opencv" ? "OpenCV + SWI-Prolog" : "SWI-Prolog"} for this frame...`);
  status(pipeline === "geometry" ? "Recognizing grid geometry..." : `Running ${pipeline === "opencv" ? "OpenCV and SWI-Prolog" : "SWI-Prolog shape finding and grouping"}...`);
  try {
    const result = await request("/omega_vision/api/v1/recognize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipeline, grid: state.grid, palette: state.palette, background: state.background,
        tolerance: Number(byId("tolerance").value), w_engine: state.wEngine, strong_edge_pct: state.strongEdgePct, old_strong_edge_pct: state.oldEdgePct, upscale: state.upscale, crack_angle_tol: state.crackAngleTol,
        ...(forceLive ? { force_live: true } : {}),
        ...(state.demoFrame ? {frame: {sequenceId: state.demoFrame.sequenceId, frameId: state.demoFrame.frameId}} : {}),
        ...(pipeline !== "geometry" && state.imageData ? {image: {base64: state.imageData}} : {}),
      }),
    });
    if (result.native) {
      const preview = new Image();
      preview.src = `data:image/png;base64,${result.preview}`;
      const debug = new Image();
      debug.src = `data:image/png;base64,${result.debug_image}`;
      await Promise.all([preview.decode(), debug.decode()]);
      if (revision === state.revision) {
        state.preview = preview;
        state.debugPreview = debug;
      }
    }
    if (revision === state.revision) showResult(result);
    else if (pageMode !== "demos") status("Input changed while recognition was running. Run again for the new input.");
    if (revision === state.revision && result.cached) {
      // Non-destructive note: never touch showAnalysisStatus here, it resets the panels.
      status(byId("status").textContent + (result.cached.needsReprocess
        ? " Served from the disk cache; Prolog rules changed since it was written \u2014 Run again reprocesses live."
        : " Served from the crawler's disk cache (up to date with the Prolog rules)."));
    }
  } catch (problem) {
    if (revision === state.revision) {
      invalidate();
      byId("result-state").textContent = "Failed";
      error(problem.message);
      showAnalysisStatus(`Analysis failed: ${problem.message}. Use Run again to retry.`, true);
      status("Recognition did not finish. Your input is unchanged.");
      renderGrid();
    } else {
      console.info("Discarded a failed analysis for a superseded frame:", problem.message);
    }
  } finally {
    state.busy = false;
    byId("recognize").disabled = state.loadingDemo;
    if (autoAnalysisPending && !state.loadingDemo && state.demoFrame) void recognize();
  }
}

function paintAt(x, y) {
  if (state.grid[y][x] === state.paint) return;
  state.grid[y][x] = state.paint;
  state.imageData = null;
  clearDemoSelection();
  invalidate();
  setView("input");
}

function point(event) {
  const rect = canvas.getBoundingClientRect();
  const width = state.result?.native && !state.editing ? state.result.width : state.grid[0].length;
  const height = state.result?.native && !state.editing ? state.result.height : state.grid.length;
  return [
    Math.min(width - 1, Math.max(0, Math.floor((event.clientX - rect.left) / rect.width * width))),
    Math.min(height - 1, Math.max(0, Math.floor((event.clientY - rect.top) / rect.height * height))),
  ];
}

canvas.addEventListener("pointerdown", (event) => {
  if (!state.grid.length) return;
  if (pageMode === "demos" && (state.view === "input" || !state.result)) return;
  canvas.focus();
  const [x, y] = point(event);
  state.cursor = [x, y];
  if ((state.view !== "input" || (state.result?.native && !state.editing)) && state.result) {
    const obj = state.result.objects.find((item) => item.cells.some(([cx, cy]) => cx === x && cy === y));
    if (obj) selectObject(obj.id);
    return;
  }
  state.drawing = true;
  canvas.setPointerCapture(event.pointerId);
  paintAt(x, y);
  renderGrid();
});
canvas.addEventListener("pointermove", (event) => {
  if (!state.grid.length) return;
  const [x, y] = point(event);
  byId("cursor-label").textContent = `${x}, ${y}`;
  if (state.drawing) {
    state.cursor = [x, y];
    paintAt(x, y);
  }
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
  canvas.addEventListener(name, () => { state.drawing = false; });
}
canvas.addEventListener("keydown", (event) => {
  if (pageMode === "demos") return;
  if (!state.grid.length) return;
  if (state.result?.native && !state.editing) return;
  const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (moves[event.key]) {
    event.preventDefault();
    const [dx, dy] = moves[event.key];
    state.cursor = [Math.max(0, Math.min(state.grid[0].length - 1, state.cursor[0] + dx)), Math.max(0, Math.min(state.grid.length - 1, state.cursor[1] + dy))];
    byId("cursor-label").textContent = state.cursor.join(", ");
    renderGrid();
  } else if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    paintAt(...state.cursor);
  }
});
canvas.addEventListener("focus", renderGrid);
canvas.addEventListener("blur", renderGrid);

function gcd(a, b) {
  while (b) [a, b] = [b, a % b];
  return a;
}

function imagePitch(pixels, width, height) {
  const equal = (a, b) => pixels[a * 4] === pixels[b * 4] && pixels[a * 4 + 1] === pixels[b * 4 + 1] && pixels[a * 4 + 2] === pixels[b * 4 + 2];
  let pitch = gcd(width, height);
  for (let y = 0; y < height && pitch > 1; y++) {
    let start = 0;
    for (let x = 1; x <= width; x++) {
      if (x === width || !equal(y * width + x, y * width + x - 1)) {
        pitch = gcd(pitch, x - start);
        start = x;
        if (pitch === 1) break;
      }
    }
  }
  for (let x = 0; x < width && pitch > 1; x++) {
    let start = 0;
    for (let y = 1; y <= height; y++) {
      if (y === height || !equal(y * width + x, (y - 1) * width + x)) {
        pitch = gcd(pitch, y - start);
        start = y;
        if (pitch === 1) break;
      }
    }
  }
  return pitch;
}

function reduceColors(colors, limit = 32) {
  const histogram = new Map();
  for (const color of colors) {
    const key = color.join(",");
    if (!histogram.has(key)) histogram.set(key, { rgb: color, count: 0 });
    histogram.get(key).count++;
  }
  const unique = [...histogram.values()];
  if (unique.length <= limit) return { colors: unique.map((item) => item.rgb), reduced: false };
  const boxes = [unique];
  while (boxes.length < limit) {
    let best = -1, range = -1, axis = 0;
    boxes.forEach((box, index) => {
      if (box.length < 2) return;
      for (let channel = 0; channel < 3; channel++) {
        const values = box.map((item) => item.rgb[channel]);
        const extent = Math.max(...values) - Math.min(...values);
        if (extent > range) { best = index; range = extent; axis = channel; }
      }
    });
    if (best < 0) break;
    const box = boxes.splice(best, 1)[0].sort((a, b) => a.rgb[axis] - b.rgb[axis]);
    const total = box.reduce((sum, item) => sum + item.count, 0);
    let count = 0, split = 1;
    for (; split < box.length; split++) {
      count += box[split - 1].count;
      if (count >= total / 2) break;
    }
    split = Math.min(split, box.length - 1);
    boxes.push(box.slice(0, split), box.slice(split));
  }
  return {
    reduced: true,
    colors: boxes.map((box) => {
      const total = box.reduce((sum, item) => sum + item.count, 0);
      return [0, 1, 2].map((channel) => Math.round(box.reduce((sum, item) => sum + item.rgb[channel] * item.count, 0) / total));
    }),
  };
}

async function importImage(file, demoFrame = null) {
  if (!file) return;
  if (!demoFrame) clearDemoSelection();
  const revision = ++state.revision;
  error();
  status("Decoding image locally...");
  let bitmap;
  try {
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("Choose a PNG, JPEG, or WebP image.");
    if (file.size > 10 * 1024 * 1024) throw new Error("Choose an image smaller than 10 MB.");
    bitmap = await createImageBitmap(file);
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Could not read the image file."));
      reader.readAsDataURL(file);
    });
    if (bitmap.width * bitmap.height > 4_194_304) throw new Error("Image is too large. Use at most 4 megapixels.");
    const source = document.createElement("canvas");
    source.width = bitmap.width;
    source.height = bitmap.height;
    const sourceContext = source.getContext("2d", { willReadFrequently: true });
    sourceContext.fillStyle = "#101725";
    sourceContext.fillRect(0, 0, source.width, source.height);
    sourceContext.drawImage(bitmap, 0, 0);
    const pixels = sourceContext.getImageData(0, 0, source.width, source.height).data;
    const pitch = imagePitch(pixels, source.width, source.height);
    const logicalWidth = source.width / pitch;
    const logicalHeight = source.height / pitch;
    const factor = Math.min(1, 64 / Math.max(logicalWidth, logicalHeight));
    const width = Math.max(1, Math.round(logicalWidth * factor));
    const height = Math.max(1, Math.round(logicalHeight * factor));
    const samples = [];
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const sx = Math.min(source.width - 1, Math.floor((x + .5) / width * source.width));
        const sy = Math.min(source.height - 1, Math.floor((y + .5) / height * source.height));
        const at = (sy * source.width + sx) * 4;
        samples.push([pixels[at], pixels[at + 1], pixels[at + 2]]);
      }
    }
    const reduced = reduceColors(samples);
    reduced.colors = [...new Map(reduced.colors.map((color) => [color.join(","), color])).values()];
    const palette = reduced.colors.map((color) => "#" + color.map((channel) => channel.toString(16).padStart(2, "0")).join(""));
    const indices = samples.map((pixel) => {
      let best = 0, distance = Infinity;
      reduced.colors.forEach((color, index) => {
        const candidate = color.reduce((sum, channel, c) => sum + (channel - pixel[c]) ** 2, 0);
        if (candidate < distance) { best = index; distance = candidate; }
      });
      return best;
    });
    const grid = Array.from({ length: height }, (_, y) => indices.slice(y * width, (y + 1) * width));
    const borderCounts = new Array(palette.length).fill(0);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      if (!x || !y || x === width - 1 || y === height - 1) borderCounts[grid[y][x]]++;
    }
    const background = borderCounts.indexOf(Math.max(...borderCounts));
    if (state.revision !== revision) return;
    const changes = [];
    if (pitch > 1) changes.push(`${pitch}px cell pitch`);
    if (factor < 1) changes.push("resampled to 64-cell maximum");
    if (reduced.reduced) changes.push("palette reduced to 32 colors");
    const note = `${file.name} \u00b7 ${source.width}\u00d7${source.height} source \u00b7 ${changes.join("; ") || "exact color sampling"}. Transparency uses a dark backdrop.`;
    const sourcePreview = new Image();
    sourcePreview.src = dataUrl;
    await sourcePreview.decode();
    if (state.revision !== revision) return;
    loadGrid({ grid, palette, background }, note, Boolean(demoFrame));
    state.imageData = dataUrl.slice(dataUrl.indexOf(",") + 1);
    state.demoFrame = demoFrame;
    state.sourcePreview = sourcePreview;
    renderGrid();
    byId("example").value = "";
    byId("example-description").textContent = "Imported image. Background was estimated from border colors; you can change it.";
    return true;
  } catch (problem) {
    if (state.revision === revision) {
      error(problem.message);
      status("Image could not be imported. Previous input was kept.");
    }
    return false;
  } finally {
    bitmap?.close();
    byId("image-file").value = "";
  }
}

function clearDemoSelection() {
  autoAnalysisPending = false;
  demoRequest++;
  state.revision++;
  state.demoFrame = null;
  state.loadingDemo = false;
  clearFrameGuide();
  byId("demo-test").value = "";
  byId("demo-frame-controls").hidden = true;
  sceneRequest++;
  byId("scene-cell").hidden = true;
  inductionRequest++;
  byId("induction-sub").hidden = true;
  byId("recognize").disabled = state.busy || !state.grid.length;
}

function selectedDemo() {
  const option = byId("demo-test").selectedOptions[0];
  const sequence = demoCatalog?.sequences.find((item) => item.id === option?.dataset.sequenceId);
  if (!sequence) return null;
  if (option.dataset.testId) {
    const test = demoCatalog?.tests.find((item) => item.id === option.dataset.testId);
    return test && test.recordings.includes(sequence.id) ? { test, sequence } : null;
  }
  return { test: null, sequence };  // on-disk recording without an authored test
}

function selectedRecording() {
  return selectedDemo()?.sequence;
}

function sequenceProperties(sequence) {
  const parts = [`${sequence.frameCount ?? sequence.frames.length} frames`];
  if (sequence.game && sequence.game !== "events_tests") parts.push(String(sequence.game));
  if (sequence.level && String(sequence.level) !== "1") parts.push(`level ${sequence.level}`);
  parts.push(sequence.processed ? "processed" : "unprocessed");
  return parts.join(" \u00b7 ");
}

function demoLabel(test, sequence) {
  if (!test) return `${sequence.id.split("/").at(-1).replaceAll("_", " ")} \u00b7 ${sequenceProperties(sequence)}`;
  if (test.recordings.length === 1) return `${test.title} \u00b7 ${sequenceProperties(sequence)}`;
  const ambiguous = test.recordings.filter((id) => {
    const other = demoCatalog.sequences.find((item) => item.id === id);
    return other.label === sequence.label && other.partition === sequence.partition;
  }).length > 1;
  const variant = ambiguous ? sequence.id.split("/").at(-1).replaceAll("_", " ") : sequence.label;
  return `${test.title} \u2014 ${variant} (${sequence.partition.replaceAll("_", " ")}) \u00b7 ${sequenceProperties(sequence)}`;
}

function frameControls() {
  const sequence = selectedRecording();
  const index = Number(byId("demo-frame").value);
  byId("previous-frame").disabled = !sequence || index <= 0;
  byId("next-frame").disabled = !sequence || index >= sequence.frames.length - 1;
  if (sequence?.frames[index]) {
    byId("demo-frame-label").textContent = `${index + 1} / ${sequence.frames.length} \u00b7 frame ${sequence.frames[index].frameId}`;
  }
}

async function loadDemoFrame() {
  const { test, sequence } = selectedDemo() || {};
  const frame = sequence?.frames[Number(byId("demo-frame").value)];
  if (!sequence || !frame) return;
  const token = ++demoRequest;
  const label = demoLabel(test, sequence);
  state.loadingDemo = true;
  invalidate(true);
  byId("recognize").disabled = true;
  frameControls();
  status(`Loading ${label}, frame ${frame.frameId}...`);
  error();
  try {
    const query = new URLSearchParams({ sequence: sequence.id, frame: frame.frameId });
    const response = await fetch(`/omega_vision/api/v1/demos/frame?${query}`);
    if (!response.ok) {
      const problem = await response.json();
      throw new Error(problem.error || `Could not load frame (${response.status}).`);
    }
    const blob = await response.blob();
    if (token !== demoRequest) return;
    const loaded = await importImage(new File([blob], `frame-${frame.frameId}.png`, { type: "image/png" }), {
      label, testId: test?.id ?? null, sequenceId: sequence.id, frameId: frame.frameId,
    });
    if (token !== demoRequest) return;
    state.loadingDemo = !loaded;
    byId("recognize").disabled = state.busy || !loaded;
    if (loaded) {
      byId("image-note").textContent = `${label} / frame ${frame.frameId} \u00b7 original recorded PNG`;
      byId("example-description").textContent = "Using a recorded demo, not a generated shape example.";
      status("Recorded frame loaded. Analysis starts automatically.");
      const url = new URL(location.href);
      if (test) url.searchParams.set("test", test.id);
      else url.searchParams.delete("test");
      url.searchParams.set("recording", sequence.id);
      url.searchParams.set("frame", frame.frameId);
      history.replaceState(null, "", url);
      if (test) loadFrameGuide(test.id, sequence.id, frame.frameId, token);
      else clearFrameGuide();
      requestDemoAnalysis();
      void loadPrevPreview(sequence, Number(byId("demo-frame").value), token);
    }
  } catch (problem) {
    if (token !== demoRequest) return;
    error(problem.message);
    showAnalysisStatus(`Frame unavailable: ${problem.message}`, true);
    status("The selected demo frame could not be loaded. Choose another frame or image.");
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function decodeDataImage(base64) {
  const image = new Image();
  image.src = `data:image/png;base64,${base64}`;
  await image.decode();
  return image;
}

const COMPANION_LABELS = { original: "Original", V: "V groups", W: "W groups", selection: "Selected parts", turtles: "Turtle (selected)" };

function companionDraw(canvasEl, key, base, isPrev) {
  if (key === "original") {
    const image = base.original;
    if (!image) return false;
    const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
    canvasEl.width = image.width * scale;
    canvasEl.height = image.height * scale;
    const brush = canvasEl.getContext("2d");
    brush.imageSmoothingEnabled = false;
    brush.drawImage(image, 0, 0, canvasEl.width, canvasEl.height);
    return true;
  }
  if (!base.result?.native) return false;
  const selection = state.selectedParts;
  const ctxByKey = {
    V: { ...base, groupsOverride: base.result.group_layers.V, parts: new Set() },
    W: { ...base, groupsOverride: base.result.group_layers.W, parts: new Set() },
    selection: { ...base, parts: selection },
    turtles: { ...base, parts: selection },
  };
  const ctx = ctxByKey[key];
  if (!ctx) return false;
  drawAnalysis(canvasEl, key === "turtles" ? "turtles" : "groups", ctx);
  return true;
}

function labelMaps(result) {
  if (result._labelMaps) return result._labelMaps;
  const regionParts = result.opencv ? result.opencv.parts : result.prolog.parts;
  const pix = new Map();
  for (const part of regionParts) {
    if (part.pixelRuns) {
      for (const [y, left, right] of part.pixelRuns) for (let x = left; x <= right; x++) pix.set(`${x},${y}`, part.id);
    } else if (part.cells) {
      for (const [x, y] of part.cells) pix.set(`${x},${y}`, part.id);
    }
  }
  const obj = new Map();
  (result.prolog.objects || []).forEach((members, index) => { for (const member of members) obj.set(member, `o${index + 1}`); });
  const grp = new Map();
  for (const group of result.group_layers.G) for (const member of group.members) grp.set(member, group.id);
  const maps = { pix, obj, grp };
  result._labelMaps = maps;
  return maps;
}

function hoverTip() {
  let tip = byId("hover-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "hover-tip";
    tip.hidden = true;
    document.body.append(tip);
  }
  return tip;
}

function showHoverTip(event, canvasEl, result) {
  const tip = hoverTip();
  if (!result?.native) { tip.hidden = true; return; }
  const rect = canvasEl.getBoundingClientRect();
  if (!rect.width || !rect.height) { tip.hidden = true; return; }
  const x = Math.floor((event.clientX - rect.left) / rect.width * result.width);
  const y = Math.floor((event.clientY - rect.top) / rect.height * result.height);
  const { pix, obj, grp } = labelMaps(result);
  const part = pix.get(`${x},${y}`);
  if (!part) { tip.hidden = true; return; }
  tip.textContent = `${part}  \u00b7  O ${obj.get(part) || "\u2014"}  \u00b7  G ${grp.get(part) || "\u2014"}`;
  tip.style.left = `${event.clientX + 12}px`;
  tip.style.top = `${event.clientY + 14}px`;
  tip.hidden = false;
}

function attachHover(canvasEl, resultGetter) {
  if (!canvasEl) return;
  canvasEl.addEventListener("mousemove", (event) => showHoverTip(event, canvasEl, resultGetter()));
  canvasEl.addEventListener("mouseleave", () => { hoverTip().hidden = true; });
}


function companionCtx(kind) {
  if (kind === "prev") return { result: state.prevResult, preview: state.prevPreview2, debug: state.prevDebug, parts: null, original: state.prevPreview, overlay: true };
  return { result: state.result, preview: state.preview, debug: state.debugPreview, parts: null, original: state.sourcePreview, overlay: true };
}

function drawCompanionCanvas(canvasEl, key, base, isPrev) {
  return companionDraw(canvasEl, key, base, isPrev);
}

function renderCompanion() {
  const cell = byId("companion-cell");
  const mode = state.companion;
  if (pageMode !== "demos" || mode === "none") { cell.hidden = true; return; }
  const ok = drawCompanionCanvas(byId("companion-canvas"), mode, companionCtx("current"), false);
  cell.hidden = !ok;
  if (ok) byId("companion-tag").textContent = `Companion: ${COMPANION_LABELS[mode]} (this frame)`;
}

function renderPrevPair() {
  const show = pageMode === "demos" && byId("show-prev").checked && Boolean(state.prevPreview);
  byId("prev-cell").hidden = !show;
  if (!show) { byId("prev-companion-cell").hidden = true; return; }
  const image = state.prevPreview;
  const canvasEl = byId("prev-canvas");
  const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
  canvasEl.width = image.width * scale;
  canvasEl.height = image.height * scale;
  const brush = canvasEl.getContext("2d");
  brush.imageSmoothingEnabled = false;
  brush.drawImage(image, 0, 0, canvasEl.width, canvasEl.height);
  const cell = byId("prev-companion-cell");
  const mode = state.companion;
  if (mode === "none") { cell.hidden = true; return; }
  if (mode !== "original" && !state.prevResult) {
    cell.hidden = true;
    void ensurePrevPipeline();
    return;
  }
  const ok = drawCompanionCanvas(byId("prev-companion-canvas"), mode, companionCtx("prev"), true);
  cell.hidden = !ok;
  if (ok) byId("prev-companion-tag").textContent = `Prev companion: ${COMPANION_LABELS[mode]}`;
}

async function runPrevPipeline(ref, token) {
  if (!ref) return;
  const pipeline = byId("pipeline").value === "geometry" ? "opencv" : byId("pipeline").value;
  try {
    const result = await request("/omega_vision/api/v1/recognize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipeline, tolerance: Number(byId("tolerance").value), w_engine: state.wEngine, strong_edge_pct: state.strongEdgePct, old_strong_edge_pct: state.oldEdgePct, upscale: state.upscale, crack_angle_tol: state.crackAngleTol,
        frame: { sequenceId: ref.sequenceId, frameId: ref.prevFrameId },
        image: { base64: ref.base64 },
      }),
    });
    if (ref !== state.prevRef || !result.native) return;
    const [preview, debug] = await Promise.all([decodeDataImage(result.preview), decodeDataImage(result.debug_image)]);
    if (ref !== state.prevRef) return;
    state.prevResult = result;
    state.prevPreview2 = preview;
    state.prevDebug = debug;
    renderPrevPair();
    void renderTwoFrame();
  } catch {
    /* previous-frame companion is best-effort and never blocks the current frame */
  }
}

async function ensurePrevPipeline() {
  if (!byId("show-prev").checked || state.companion === "none" || state.companion === "original") return;
  if (state.prevResult || !state.prevRef || state.prevBusy) return;
  const ref = state.prevRef;
  state.prevBusy = true;
  try {
    await runPrevPipeline(ref, demoRequest);
  } finally {
    state.prevBusy = false;
  }
}

async function loadPrevPreview(sequence, index, token) {
  const prev = sequence.frames[index - 1];
  if (!prev) {
    // Genuinely no previous frame (first frame): clear prev state and hide the prev cell.
    state.prevPreview = null;
    state.prevResult = null;
    state.prevPreview2 = null;
    state.prevDebug = null;
    state.prevRef = null;
    renderPrevPair();
    if (state.view === "prev") renderGrid();
    return;
  }
  try {
    const query = new URLSearchParams({ sequence: sequence.id, frame: prev.frameId });
    const response = await fetch(`/omega_vision/api/v1/demos/frame?${query}`);
    if (!response.ok || token !== demoRequest) return;
    const blob = await response.blob();
    if (token !== demoRequest) return;
    const base64 = await blobToBase64(blob);
    const image = await decodeDataImage(base64);
    if (token !== demoRequest) return;
    // Swap to the new previous frame only once it's decoded (old one stays visible until now).
    state.prevPreview = image;
    state.prevRef = { sequenceId: sequence.id, prevFrameId: prev.frameId, base64 };
    state.prevResult = null;
    state.prevPreview2 = null;
    state.prevDebug = null;
    renderPrevPair();
    if (state.view === "prev") renderGrid();
    await ensurePrevPipeline();
  } catch {
    /* previous-frame context is best-effort and never blocks analysis */
  }
}

function clearFrameGuide() {
  byId("frame-guide").hidden = true;
  byId("frame-guide-body").replaceChildren();
}

let trackerRequest = 0;
function drawTrackerOverlay(body, tracking, statusColors) {
  // Ground the hypotheses ON the image: draw the current frame, box present entities
  // (colored by observed status), ghost the gone ones (dashed) at their last-known spot,
  // and label each with its top hypothesis + confidence. This is the visual layer the
  // downstream reasoner hypothesizes over.
  const image = state.sourcePreview;
  if (!image) return;
  const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
  const canvas = document.createElement("canvas");
  canvas.width = image.width * scale;
  canvas.height = image.height * scale;
  canvas.className = "tracker-overlay";
  const brush = canvas.getContext("2d");
  brush.imageSmoothingEnabled = false;
  brush.drawImage(image, 0, 0, canvas.width, canvas.height);
  brush.font = "11px system-ui, sans-serif";
  brush.textBaseline = "top";
  brush.lineWidth = Math.max(1, scale);
  const label = (x, y, text, color) => {
    const w = brush.measureText(text).width + 6;
    brush.fillStyle = "rgba(0,0,0,0.72)";
    brush.fillRect(x, y, w, 14);
    brush.fillStyle = color;
    brush.fillText(text, x + 3, y + 2);
  };
  const topHyp = (h) => (h && h.length) ? ` ? ${h[0].label.split(":")[0]} ${Math.round(h[0].confidence * 100)}%` : "";
  for (const e of tracking.present) {
    if (!e.bounds) continue;
    const [x, y, w, h] = e.bounds.map((v) => v * scale);
    const color = statusColors[e.status] || "#c8d3e6";
    brush.setLineDash([]);
    brush.strokeStyle = color;
    brush.strokeRect(x + 0.5, y + 0.5, Math.max(1, w), Math.max(1, h));
    label(x, Math.max(0, y - 14), `${e.eid} ${e.status}${topHyp(e.hypotheses)}`, color);
  }
  for (const e of tracking.occluded) {
    if (!e.bounds) continue;
    const [x, y, w, h] = e.bounds.map((v) => v * scale);
    brush.setLineDash([Math.max(2, scale * 2), Math.max(2, scale * 2)]);
    brush.strokeStyle = statusColors.occluded;
    brush.strokeRect(x + 0.5, y + 0.5, Math.max(1, w), Math.max(1, h));
    label(x, Math.max(0, y - 14), `${e.eid} gone${topHyp(e.hypotheses)}`, statusColors.occluded);
  }
  brush.setLineDash([]);
  body.append(canvas);
}

const trackFed = {};  // sequenceId -> Set of frame orders already fed to the tracker
async function recognizeOrder(sequence, order) {
  // Recognize one earlier frame so it can be fed to the tracker during catch-up. Uses
  // the same engine params as the live pipeline so identities line up with the current frame.
  const frame = sequence.frames[order];
  const resp = await fetch(`/omega_vision/api/v1/demos/frame?${new URLSearchParams({ sequence: sequence.id, frame: frame.frameId })}`);
  if (!resp.ok) throw new Error(`frame ${frame.frameId} unavailable`);
  const base64 = await blobToBase64(await resp.blob());
  const pipeline = byId("pipeline").value === "geometry" ? "opencv" : byId("pipeline").value;
  const result = await request("/omega_vision/api/v1/recognize", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pipeline, tolerance: Number(byId("tolerance").value), w_engine: state.wEngine,
      strong_edge_pct: state.strongEdgePct, old_strong_edge_pct: state.oldEdgePct,
      upscale: state.upscale, crack_angle_tol: state.crackAngleTol,
      frame: { sequenceId: sequence.id, frameId: frame.frameId }, image: { base64 },
    }),
  });
  if (!result.native) throw new Error(`frame ${frame.frameId} not analyzable`);
  return {
    objects: result.objects.map((o) => ({ id: o.id, shape_id: o.shape_id, color: o.color, area: o.area, bounds: o.bounds })),
    width: result.width, height: result.height,
  };
}

// ---- Hover-to-locate: highlight one or more e# ids on whichever frame shows them ----
// An entity present on the current frame is highlighted on the current image; one that is
// gone this frame is highlighted on the previous image instead. If neither image is visible
// on screen, a small pop-up of that frame is shown with the location(s) marked.
function isOnScreen(el) {
  if (!el || el.hidden || el.offsetParent === null) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4) return false;
  const vh = window.innerHeight || document.documentElement.clientHeight;
  const vw = window.innerWidth || document.documentElement.clientWidth;
  return r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
}

// Bounds (processed image coords) for an entity, plus which frame it lives on.
function entityLocation(eid) {
  const cur = state.twoFrame?.entityBounds?.[eid] || state.entityBounds?.[eid];
  if (cur) return { bounds: cur, frame: "current" };
  const prev = state.twoFrame?.prevEntityBounds?.[eid];
  if (prev) return { bounds: prev, frame: "previous" };
  return null;
}

function frameView(which) {
  if (which === "previous") {
    return { canvas: byId("prev-canvas"), cell: byId("prev-cell"),
             w: state.prevResult?.width, h: state.prevResult?.height, image: state.prevPreview };
  }
  return { canvas: byId("image-canvas"), cell: byId("current-cell"),
           w: state.result?.width, h: state.result?.height, image: state.preview };
}

// Draw absolutely-positioned highlight boxes over an inline frame canvas.
function drawInlineBoxes(view, boundsList) {
  const { canvas, cell, w, h } = view;
  if (!canvas || !cell || !w || !h) return false;
  cell.style.position = "relative";
  const cw = canvas.clientWidth, ch = canvas.clientHeight;
  let layer = cell.querySelector(".entity-highlight-layer");
  if (!layer) { layer = document.createElement("div"); layer.className = "entity-highlight-layer"; cell.appendChild(layer); }
  layer.replaceChildren();
  for (const b of boundsList) {
    const box = document.createElement("div");
    box.className = "entity-highlight";
    box.style.left = `${canvas.offsetLeft + (b[0] / w) * cw}px`;
    box.style.top = `${canvas.offsetTop + (b[1] / h) * ch}px`;
    box.style.width = `${(b[2] / w) * cw}px`;
    box.style.height = `${(b[3] / h) * ch}px`;
    layer.appendChild(box);
  }
  layer.hidden = false;
  return true;
}

// Floating pop-up of a frame with the location(s) marked, used when no inline image is visible.
function showLocationPopup(view, boundsList, label) {
  const { image, w, h } = view;
  if (!image || !w || !h) return;
  let pop = byId("entity-popup");
  if (!pop) {
    pop = document.createElement("div");
    pop.id = "entity-popup";
    pop.className = "entity-popup";
    pop.innerHTML = '<div class="entity-popup-tag"></div><canvas></canvas>';
    document.body.appendChild(pop);
  }
  const maxSide = 240;
  const scale = Math.max(1, Math.floor(maxSide / Math.max(image.width, image.height))) ||
                (maxSide / Math.max(image.width, image.height));
  const cv = pop.querySelector("canvas");
  cv.width = Math.round(image.width * scale);
  cv.height = Math.round(image.height * scale);
  const brush = cv.getContext("2d");
  brush.imageSmoothingEnabled = false;
  brush.drawImage(image, 0, 0, cv.width, cv.height);
  brush.strokeStyle = "#ffd34d";
  brush.lineWidth = 2;
  const sx = cv.width / w, sy = cv.height / h;
  for (const b of boundsList) brush.strokeRect(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy);
  pop.querySelector(".entity-popup-tag").textContent = label;
  pop.hidden = false;
}

function highlightEntities(eids, groupLabel, forcePopup) {
  clearHighlight();
  hoverTarget = { eids, groupLabel };  // remembered so Ctrl can toggle the pop-up live
  const byFrame = { current: [], previous: [] };
  for (const eid of eids) {
    const loc = entityLocation(eid);
    if (loc) byFrame[loc.frame].push(loc.bounds);
  }
  // Prefer the current frame; only fall back to the previous frame for entities that are gone.
  const which = byFrame.current.length ? "current" : "previous";
  const bounds = byFrame[which];
  if (!bounds.length) return;
  const view = frameView(which);
  const label = (groupLabel ? `${groupLabel} \u00b7 ` : "") +
                (which === "previous" ? "previous frame" : "this frame");
  // Ctrl held (or no inline image on screen) forces the floating locator pop-up.
  if (forcePopup || ctrlDown || !isOnScreen(view.canvas)) showLocationPopup(view, bounds, label);
  else drawInlineBoxes(view, bounds);
}
function highlightEntity(eid) { highlightEntities([eid]); }
function clearHighlight() {
  hoverTarget = null;
  document.querySelectorAll(".entity-highlight-layer").forEach((l) => (l.hidden = true));
  const box = byId("entity-highlight"); if (box) box.hidden = true;
  const pop = byId("entity-popup"); if (pop) pop.hidden = true;
}

// Grouping tree hover: outline the hovered group's/member's regions (g/v/w/e) directly on the
// group preview canvas to the right of the tree, so hovering a node shows exactly what it covers.
function highlightGroupMembers(memberIds) {
  const preview = byId("group-preview");
  const cell = preview?.parentElement;
  if (!preview || !cell || !state.result) return;
  const map = new Map((state.result.objects || []).map((obj) => [obj.id, obj.bounds]));
  const bounds = memberIds.map((id) => map.get(id)).filter(Boolean);
  clearHighlight();
  if (!bounds.length) return;
  drawInlineBoxes({ canvas: preview, cell, w: state.result.width, h: state.result.height }, bounds);
}

// Track the Ctrl key so hovering a token can always pop up a locating frame while it is held.
let ctrlDown = false;
let hoverTarget = null;  // { eids, groupLabel } currently hovered, for live Ctrl toggle
function onCtrlChange(event) {
  const down = event.ctrlKey;
  if (down === ctrlDown) return;
  ctrlDown = down;
  if (hoverTarget) highlightEntities(hoverTarget.eids, hoverTarget.groupLabel);  // re-render in place
}
window.addEventListener("keydown", onCtrlChange);
window.addEventListener("keyup", onCtrlChange);

// Build a stable group-id -> member e# list map from the current two-frame deduction.
function groupMembersMap() {
  const map = new Map();
  for (const g of (state.twoFrame?.groups || [])) {
    const members = (g.members && g.members.length) ? g.members : (g.lost || []);
    if (members.length) map.set(g.id, members);
  }
  return map;
}

function eidTokens(ids) {
  // Render a comma-separated list of e# ids as hover-highlightable tokens.
  const frag = document.createDocumentFragment();
  ids.forEach((id, i) => {
    if (i) frag.append(document.createTextNode(", "));
    const span = document.createElement("span");
    span.className = "eid-token";
    span.dataset.eid = id;
    span.textContent = id;
    span.addEventListener("mouseenter", () => highlightEntity(id));
    span.addEventListener("mouseleave", clearHighlight);
    frag.append(span);
  });
  return frag;
}

// Render G#/W# group ids as hover tokens that highlight every member e# at once. A group is
// essentially an AKA for its member set, so hovering it marks all of them on the frame.
function gidTokens(gids) {
  const frag = document.createDocumentFragment();
  const members = groupMembersMap();
  gids.forEach((gid, i) => {
    if (i) frag.append(document.createTextNode(", "));
    const span = document.createElement("span");
    span.className = "gid-token";
    span.dataset.gid = gid;
    span.textContent = gid;
    const ids = members.get(gid) || [];
    span.addEventListener("mouseenter", () => highlightEntities(ids, gid));
    span.addEventListener("mouseleave", clearHighlight);
    frag.append(span);
  });
  return frag;
}

async function renderTracker() {
  const panel = byId("interframe");
  const sub = byId("tracker-sub");
  const body = byId("tracker-body");
  if (pageMode !== "demos" || !state.result?.native || !state.demoFrame) {
    sub.hidden = true;
    return;
  }
  panel.hidden = false;
  sub.hidden = false;
  const token = ++trackerRequest;
  const objects = state.result.objects.map((obj) => ({ id: obj.id, shape_id: obj.shape_id, color: obj.color, area: obj.area, bounds: obj.bounds }));
  const clip = state.demoFrame.sequenceId;
  const order = Number(byId("demo-frame").value);
  const fed = (trackFed[clip] = trackFed[clip] || new Set());
  try {
    // The tracker only ever steps forward. If the user landed past frame 0 without
    // stepping (e.g. a deep link), advance through every un-fed earlier frame in order
    // first -- they wait while the system slowly catches memory up, rather than the
    // tracker teleporting and mislabelling everything as brand new.
    const sequence = selectedRecording();
    if (sequence) {
      const missing = [];
      for (let k = 0; k < order; k++) if (!fed.has(k)) missing.push(k);
      if (missing.length) {
        body.replaceChildren();
        const prog = document.createElement("p");
        prog.className = "hint";
        body.append(prog);
        for (const k of missing) {
          if (token !== trackerRequest) return;
          prog.textContent = `Advancing memory \u2014 frame ${k + 1} / ${order + 1} (the tracker only steps forward)\u2026`;
          try {
            const r = await recognizeOrder(sequence, k);
            if (token !== trackerRequest) return;
            await request("/omega_vision/api/v1/track", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ sequenceId: clip, order: k, width: r.width, height: r.height, objects: r.objects }),
            });
            fed.add(k);
          } catch { /* an unreadable in-between frame is skipped; memory stays best-effort */ }
        }
      }
    }
    const tracking = await request("/omega_vision/api/v1/track", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sequenceId: clip, order,
        width: state.result.width, height: state.result.height, objects,
      }),
    });
    fed.add(order);
    if (token !== trackerRequest) return;
    // Publish the current frame's r# -> e# map so the parts grouping (G/W/V) can show stable
    // identities, then re-render the grouping in place if it's on screen.
    const entityMap = {};
    for (const p of tracking.present) if (p.current) entityMap[p.current] = p.eid;
    state.entityMap = entityMap;
    // e# -> bounds on the current frame, so hovering an e# id can highlight it on the image.
    const entityBounds = {};
    for (const obj of state.result.objects) { const e = entityMap[obj.id]; if (e) entityBounds[e] = obj.bounds; }
    state.entityBounds = entityBounds;
    if (state.result?.native && !byId("parts-grouping-panel").hidden) renderPartsGrouping();
    body.replaceChildren();
    const summary = document.createElement("p");
    summary.className = "hint";
    summary.textContent = `${tracking.entityCount} entities tracked \u00b7 ${tracking.present.length} visible now \u00b7 ${tracking.occluded.length} remembered (occluded).`;
    body.append(summary);
    // The per-entity moves/rotations live in the Two-frame block above; here we keep only
    // the tracker's unique clip-memory: the change-layer overview and remembered (occluded)
    // entities that have been gone for one or more frames.
    if (tracking.layers && tracking.layers.length) {
      const stack = document.createElement("p");
      stack.className = "hint";
      stack.textContent = "Change layers: " + tracking.layers
        .map((layer) => `${layer.kind} \u00d7${layer.entities.length}`).join("  \u00b7  ");
      body.append(stack);
    }
    if (tracking.occluded.length) {
      const occ = document.createElement("p");
      occ.className = "hint";
      occ.textContent = `Remembered (occluded): ${tracking.occluded.map((e) => `${e.eid} (${e.framesSinceSeen}f ago)`).join(", ")}.`;
      body.append(occ);
    }
  } catch (problem) {
    if (token !== trackerRequest) return;
    body.replaceChildren();
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `Tracking unavailable: ${problem.message}`;
    body.append(note);
  }
}

let frameDiffRequest = 0;
async function renderFrameDiff() {
  const sub = byId("frame-diff-sub");
  const body = byId("frame-diff-body");
  // Needs a previous frame. N/A on the first frame -> hide; otherwise keep the current
  // diff until the new frame's diff is computed (don't collapse while advancing).
  if (pageMode !== "demos" || !hasPrevFrame()) {
    sub.hidden = true;
    return;
  }
  if (!state.imageData || !state.prevRef?.base64) return;
  byId("interframe").hidden = false;
  sub.hidden = false;
  const token = ++frameDiffRequest;
  body.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "hint";
  loading.textContent = "Diffing against the previous frame\u2026";
  body.append(loading);
  try {
    const diff = await request("/omega_vision/api/v1/diff", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current: state.imageData, previous: state.prevRef.base64 }),
    });
    if (token !== frameDiffRequest) return;
    body.replaceChildren();
    const image = await decodeDataImage(diff.image.split(",")[1]);
    if (token !== frameDiffRequest) return;
    const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
    const canvas = document.createElement("canvas");
    canvas.width = image.width * scale;
    canvas.height = image.height * scale;
    canvas.className = "tracker-overlay";
    const brush = canvas.getContext("2d");
    brush.imageSmoothingEnabled = false;
    brush.drawImage(image, 0, 0, canvas.width, canvas.height);
    body.append(canvas);
    const c = diff.counts;
    const pct = (n) => `${Math.round((n / c.total) * 100)}%`;
    const summary = document.createElement("p");
    summary.className = "hint";
    summary.innerHTML =
      `<span style="color:#c8d3e6">stable ${pct(c.stable)}</span> \u00b7 ` +
      `<span style="color:#3ce87a">appeared ${pct(c.appeared)}</span> \u00b7 ` +
      `<span style="color:#ff6b6b">disappeared ${pct(c.disappeared)}</span> \u00b7 ` +
      `<span style="color:#f0d24a">changed ${pct(c.changed)}</span>`;
    body.append(summary);
    for (const [kind, regions] of Object.entries(diff.regions)) {
      if (!regions.length) continue;
      const line = document.createElement("p");
      line.className = "hint";
      const top = regions.slice(0, 3).map((r) => {
        const h = r.hypotheses?.[0];
        return `[${r.bounds.join(",")}] ${r.area}px${h ? ` ? ${h.label.split(":")[0]} ${Math.round(h.confidence * 100)}%` : ""}`;
      }).join("  \u00b7  ");
      line.textContent = `${kind} (${regions.length}): ${top}${regions.length > 3 ? " \u2026" : ""}`;
      body.append(line);
    }
  } catch (problem) {
    if (token !== frameDiffRequest) return;
    body.replaceChildren();
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `Frame diff unavailable: ${problem.message}`;
    body.append(note);
  }
}

let twoFrameRequest = 0;
function drawTwoFrameOverlay(body, deduction) {
  // Visualise the two-frame deduction ON the current image: a rotation arc for rotated
  // objects and a dashed marker where an object is occluded / a prev object vanished.
  const image = state.sourcePreview;
  if (!image) return;
  const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
  const canvas = document.createElement("canvas");
  canvas.width = image.width * scale;
  canvas.height = image.height * scale;
  canvas.className = "tracker-overlay";
  const brush = canvas.getContext("2d");
  brush.imageSmoothingEnabled = false;
  brush.drawImage(image, 0, 0, canvas.width, canvas.height);
  brush.lineWidth = Math.max(1, scale);
  brush.font = "11px system-ui, sans-serif";
  brush.textBaseline = "top";
  const label = (x, y, text, color) => {
    const w = brush.measureText(text).width + 6;
    brush.fillStyle = "rgba(0,0,0,0.72)";
    brush.fillRect(x, y, w, 14);
    brush.fillStyle = color;
    brush.fillText(text, x + 3, y + 2);
  };
  for (const m of deduction.matches) {
    if (m.cx == null) continue;
    const x = m.cx * scale, y = m.cy * scale;
    if (m.rotationDeg != null && /rotated/.test(m.transform)) {
      const r = Math.max(10, scale * 8);
      brush.strokeStyle = "#5fd0ff";
      brush.beginPath();
      const dir = m.rotationDeg >= 0 ? 1 : -1;
      brush.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + dir * Math.PI * 1.4, dir < 0);
      brush.stroke();
      const ex = x + r * Math.cos(-Math.PI / 2 + dir * Math.PI * 1.4);
      const ey = y + r * Math.sin(-Math.PI / 2 + dir * Math.PI * 1.4);
      brush.fillStyle = "#5fd0ff";
      brush.beginPath();
      brush.arc(ex, ey, Math.max(2, scale), 0, Math.PI * 2);
      brush.fill();
      label(x + r + 2, y - 7, `\u21bb ${m.rotationDeg}\u00b0`, "#5fd0ff");
    }
    if (m.occludedBy) {
      brush.strokeStyle = "#ff6b6b";
      brush.setLineDash([Math.max(2, scale * 2), Math.max(2, scale * 2)]);
      brush.beginPath();
      brush.arc(x, y, Math.max(10, scale * 7), 0, Math.PI * 2);
      brush.stroke();
      brush.setLineDash([]);
      label(x + 8, y + 8, `occluded by ${m.occludedBy}`, "#ff6b6b");
    }
  }
  for (const d of deduction.disappeared) {
    if (d.cx == null || !d.occludedBy) continue;
    const x = d.cx * scale, y = d.cy * scale;
    brush.strokeStyle = "#ffb454";
    brush.setLineDash([Math.max(2, scale * 2), Math.max(2, scale * 2)]);
    brush.strokeRect(x - 8, y - 8, 16, 16);
    brush.setLineDash([]);
    label(x + 8, y - 7, `${d.previous} occluded by ${d.occludedBy}`, "#ffb454");
  }
  body.append(canvas);
}
function hasPrevFrame() {
  return pageMode === "demos" && Boolean(state.demoFrame) && Number(byId("demo-frame").value) > 0;
}
async function renderTwoFrame() {
  const sub = byId("two-frame-sub");
  const body = byId("two-frame-body");
  // Genuinely not applicable -> hide. Data merely not ready yet -> keep current content
  // (so advancing a frame doesn't collapse the section; it updates in place when ready).
  if (pageMode !== "demos" || !byId("show-prev").checked || !hasPrevFrame()) {
    sub.hidden = true;
    return;
  }
  if (!state.result?.native || !state.prevResult?.native) return;
  byId("interframe").hidden = false;
  sub.hidden = false;
  const token = ++twoFrameRequest;
  const runsById = (result) => new Map((result.opencv?.parts || []).map((p) => [p.id, p.pixelRuns]));
  const pick = (result) => {
    const runs = runsById(result);
    return { objects: result.objects.map((obj) => ({ id: obj.id, shape_id: obj.shape_id, color: obj.color, area: obj.area, bounds: obj.bounds, pixelRuns: runs.get(obj.id) || null })) };
  };
  const pickGroups = (result) => ({
    G: (result.group_layers?.G || []).map((g) => g.members),
    W: (result.group_layers?.W || []).map((g) => g.members),
  });
  const hypText = (h) => (h && h.length) ? " \u2014 maybe " + h.map((x) => `${x.label} (${Math.round(x.confidence * 100)}%)`).join(" / ") : "";
  try {
    const deduction = await request("/omega_vision/api/v1/deduce2", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current: pick(state.result), previous: pick(state.prevResult),
        currentGroups: pickGroups(state.result), previousGroups: pickGroups(state.prevResult),
        sequenceId: state.demoFrame.sequenceId,
        currentOrder: Number(byId("demo-frame").value),
        previousOrder: Number(byId("demo-frame").value) - 1,
        width: state.result.width, height: state.result.height,
      }),
    });
    if (token !== twoFrameRequest) return;
    state.twoFrame = deduction;
    state.deductionFiles = deduction.files || [];
    if (state.result?.metta) renderOutputEditor();  // add the deduction tabs (e#-only)
    body.replaceChildren();
    // Index group-level changes so they can be folded into the matching entity lines
    // (moved -> the moved line, gone -> the gone line) instead of a duplicated section.
    const movedGroupsByVec = new Map();
    const goneGroupIds = [];
    const otherGroupChanges = [];
    for (const g of (deduction.groups || [])) {
      if (g.moved) { const k = g.moved.join(","); if (!movedGroupsByVec.has(k)) movedGroupsByVec.set(k, []); movedGroupsByVec.get(k).push(g.id); }
      else if (g.gone) { goneGroupIds.push(g.id); }
      else if ((g.gained || []).length || (g.lost || []).length) { otherGroupChanges.push(g); }
    }
    if (deduction.matches.length) {
      // Explained movers (their motion is a consequence of a nearby rotation) are folded
      // out of the independent "moved" list and attached to the pivot's rotation line.
      const explainedBy = new Map();
      const carried = new Map();
      for (const x of (deduction.explanations || [])) {
        explainedBy.set(x.entity, x.by);
        if (!carried.has(x.by)) carried.set(x.by, []);
        carried.get(x.by).push(x.entity);
      }
      // Group by transform category so each category is ONE line with its ids inline.
      const groups = new Map();
      for (const match of deduction.matches) {
        if (explainedBy.has(match.current)) continue;  // folded into the pivot's rotation
        const key = match.transform;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(match);
      }
      for (const [key, ms] of groups) {
        if (key === "stationary") continue;  // stationary = unchanged; shown as a count only
        const ids = ms.map((m) => m.current);
        const line = document.createElement("p");
        line.className = "hint deduction-line";
        const strong = document.createElement("strong");
        strong.textContent = `${key} (${ids.length}): `;
        line.append(strong, eidTokens(ids));
        if (/moved/.test(key)) {
          const gids = movedGroupsByVec.get(`${ms[0].dx},${ms[0].dy}`) || [];
          if (gids.length) { line.append(document.createTextNode("  \u00b7 groups: ")); line.append(gidTokens(gids)); }
          else if (ids.length >= 2) {
            const flag = document.createElement("span");
            flag.className = "no-group-flag";
            flag.textContent = "  \u00b7 \u26a0 no G/W group for this set";
            line.append(flag);
          }
        }
        if (/rotated/.test(key)) {
          const carriedIds = ids.flatMap((id) => carried.get(id) || []);
          if (carriedIds.length) { line.append(document.createTextNode("  \u00b7 carries ")); line.append(eidTokens(carriedIds)); }
        }
        body.append(line);
      }
      const stationaryN = groups.has("stationary") ? groups.get("stationary").length : 0;
      if (stationaryN) {
        const note = document.createElement("p");
        note.className = "hint";
        note.textContent = `+ ${stationaryN} stationary (unchanged).`;
        body.append(note);
      }
    } else {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = "No confident object correspondence between the two frames.";
      body.append(note);
    }
    if (deduction.disappeared.length) {
      const line = document.createElement("p");
      line.className = "hint deduction-line";
      const strong = document.createElement("strong");
      strong.textContent = `gone (${deduction.disappeared.length}): `;
      line.append(strong);
      // Group the gone entities by their occluder so a shared occluder reads once:
      // "occluded by e9: e17, e19, e20". Entities with no identified occluder list plainly.
      const byOcc = new Map();
      const noOcc = [];
      for (const d of deduction.disappeared) {
        if (d.occludedBy) { if (!byOcc.has(d.occludedBy)) byOcc.set(d.occludedBy, []); byOcc.get(d.occludedBy).push(d.previous); }
        else noOcc.push(d.previous);
      }
      let first = true;
      for (const [occ, ids] of byOcc) {
        if (!first) line.append(document.createTextNode(" \u00b7 "));
        first = false;
        line.append(document.createTextNode("occluded by "), eidTokens([occ]), document.createTextNode(": "), eidTokens(ids));
      }
      if (noOcc.length) {
        if (!first) line.append(document.createTextNode(" \u00b7 "));
        line.append(eidTokens(noOcc));
      }
      if (goneGroupIds.length) { line.append(document.createTextNode("  \u00b7 groups: ")); line.append(gidTokens(goneGroupIds)); }
      body.append(line);
    }
    if (deduction.appeared.length) {
      const line = document.createElement("p");
      line.className = "hint deduction-line";
      const strong = document.createElement("strong");
      strong.textContent = `new (${deduction.appeared.length}): `;
      line.append(strong);
      // Symmetric with "gone": group by the occluder the entity was revealed from behind.
      const byRev = new Map();
      const noRev = [];
      for (const a of deduction.appeared) {
        if (a.revealedFrom) { if (!byRev.has(a.revealedFrom)) byRev.set(a.revealedFrom, []); byRev.get(a.revealedFrom).push(a.current); }
        else noRev.push(a.current);
      }
      let firstA = true;
      for (const [rev, ids] of byRev) {
        if (!firstA) line.append(document.createTextNode(" \u00b7 "));
        firstA = false;
        line.append(document.createTextNode("revealed from "), eidTokens([rev]), document.createTextNode(": "), eidTokens(ids));
      }
      if (noRev.length) {
        if (!firstA) line.append(document.createTextNode(" \u00b7 "));
        line.append(eidTokens(noRev));
      }
      body.append(line);
    }
    // Any remaining group changes not already folded into moved/gone lines.
    for (const g of otherGroupChanges) {
      const parts = [];
      if ((g.gained || []).length) parts.push(`gained ${g.gained.join(", ")}`);
      const occ = (g.occludedMembers || []).map(([e, by]) => `${e} (occl. by ${by})`);
      const plainLost = (g.lost || []).filter((e) => !(g.occludedMembers || []).some(([m]) => m === e));
      if (occ.length) parts.push(`lost ${occ.join(", ")}`);
      if (plainLost.length) parts.push(`lost ${plainLost.join(", ")}`);
      if (!parts.length) continue;
      const line = document.createElement("p");
      line.className = "hint deduction-line";
      const strong = document.createElement("strong");
      strong.textContent = `${g.id}: `;
      line.append(strong, document.createTextNode(parts.join(" \u00b7 ")));
      body.append(line);
    }
    // Suggested groups: co-behaving sets (moved/gone together) with no backing G/W group.
    for (const s of (deduction.suggestedGroups || [])) {
      const line = document.createElement("p");
      line.className = "hint deduction-line";
      const flag = document.createElement("span");
      flag.className = "no-group-flag";
      flag.textContent = "\u26a0 suggest group: ";
      const why = s.reason === "gone_together" ? `gone together (occl. by ${s.occludedBy})`
        : s.reason === "revealed_together" ? `revealed together (occluder ${s.revealedFrom} left) \u2014 assign a new W/G and read its turtle to identify the object`
        : `moved together (${s.dx}, ${s.dy})`;
      line.append(flag, eidTokens(s.members), document.createTextNode(` \u2014 ${why}; no G/W backs this set`));
      body.append(line);
    }
    // Rotation can explain a neighbour's apparent move (it didn't move on its own).
    for (const x of (deduction.explanations || [])) {
      const line = document.createElement("p");
      line.className = "hint deduction-line";
      line.append(document.createTextNode("explained: "), eidTokens([x.entity]),
        document.createTextNode(" move "), document.createTextNode("\u21d0 "),
        document.createTextNode("rotated("), eidTokens([x.by]),
        document.createTextNode(`, ${x.degrees}\u00b0) \u21d2 \u00ac independent_motion(`), eidTokens([x.entity]),
        document.createTextNode(")"));
      body.append(line);
    }
    renderDeductionImages();
  } catch (problem) {
    if (token !== twoFrameRequest) return;
    body.replaceChildren();
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `Two-frame deduction unavailable: ${problem.message}`;
    body.append(note);
  }
}

function paintPartsById(canvasEl, result, colorFor) {
  const scale = Math.max(1, Math.floor(360 / Math.max(result.width, result.height)));
  canvasEl.width = result.width * scale;
  canvasEl.height = result.height * scale;
  const brush = canvasEl.getContext("2d");
  brush.imageSmoothingEnabled = false;
  const parts = result.opencv ? result.opencv.parts : result.prolog.parts;
  for (const part of parts) {
    const color = colorFor(part);
    if (!color) continue;
    brush.fillStyle = color;
    if (part.pixelRuns) {
      for (const [y, left, right] of part.pixelRuns) brush.fillRect(left * scale, y * scale, (right - left + 1) * scale, scale);
    } else if (part.cells) {
      for (const [x, y] of part.cells) brush.fillRect(x * scale, y * scale, scale, scale);
    }
  }
  return { brush, scale };
}

function objectBoundsMap(result) {
  return new Map(result.objects.map((obj) => [obj.id, obj.bounds]));
}

async function renderDeductionImages() {
  const panel = byId("layer-images");
  const deduction = state.twoFrame;
  if (pageMode !== "demos" || !byId("show-prev").checked || !hasPrevFrame()) {
    panel.hidden = true;
    return;
  }
  if (!deduction || !state.result?.native || !state.prevResult?.native) return;
  panel.hidden = false;

  const drawNatural = (canvasEl, img) => {
    canvasEl.width = img.width;
    canvasEl.height = img.height;
    const b = canvasEl.getContext("2d");
    b.imageSmoothingEnabled = false;
    b.drawImage(img, 0, 0);
    return b;
  };
  const drawArrows = (brush) => {
    const bounds = objectBoundsMap(state.result);
    brush.strokeStyle = "#ffd34d";
    brush.fillStyle = "#ffd34d";
    brush.lineWidth = 1;
    for (const match of deduction.matches) {
      if (match.dx === 0 && match.dy === 0) continue;
      const b = bounds.get(match.currentNative);
      if (!b) continue;
      const cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2;
      const px = cx - match.dx, py = cy - match.dy;
      brush.beginPath();
      brush.moveTo(px, py);
      brush.lineTo(cx, cy);
      brush.stroke();
      const angle = Math.atan2(cy - py, cx - px);
      brush.beginPath();
      brush.moveTo(cx, cy);
      brush.lineTo(cx - 5 * Math.cos(angle - 0.4), cy - 5 * Math.sin(angle - 0.4));
      brush.lineTo(cx - 5 * Math.cos(angle + 0.4), cy - 5 * Math.sin(angle + 0.4));
      brush.closePath();
      brush.fill();
    }
  };

  // Prefer the server-composited layers (built in Python so a merged background exists even
  // without a browser). Fall back to client compositing only if the server didn't send them.
  const layers = deduction.layers;
  if (layers && layers.layer0Image && layers.layer1Image) {
    const [l0, l1] = await Promise.all([
      decodeDataImage(layers.layer0Image.split(",")[1]),
      decodeDataImage(layers.layer1Image.split(",")[1]),
    ]);
    drawNatural(byId("same-canvas"), l0);
    const layer1Source = document.createElement("canvas");
    drawNatural(layer1Source, l1);          // clean movers image feeds the pipeline
    const movedBrush = drawNatural(byId("moved-canvas"), l1);
    drawArrows(movedBrush);                  // display copy gets motion arrows
    void ensureLayerPipeline("layer0", byId("same-canvas"));
    void ensureLayerPipeline("layer1", layer1Source);
    return;
  }

  // ---- Fallback: composite in the browser (older path) ----
  const stationaryCurr = new Set(deduction.matches.filter((m) => m.dx === 0 && m.dy === 0).map((m) => m.currentNative));
  const stationaryPrev = new Set(deduction.matches.filter((m) => m.dx === 0 && m.dy === 0).map((m) => m.previousNative));
  const movedCurr = new Set(deduction.matches.filter((m) => m.dx !== 0 || m.dy !== 0).map((m) => m.currentNative));
  const bgPixels = (result, idSet) => {
    const map = new Map();
    const parts = result.opencv ? result.opencv.parts : result.prolog.parts;
    for (const part of parts) {
      if (!idSet.has(part.id)) continue;
      if (part.pixelRuns) { for (const [y, l, r] of part.pixelRuns) for (let x = l; x <= r; x++) map.set(y * result.width + x, part.color); }
      else if (part.cells) { for (const [x, y] of part.cells) map.set(y * result.width + x, part.color); }
    }
    return map;
  };
  const currBg = bgPixels(state.result, stationaryCurr);
  const prevBg = bgPixels(state.prevResult, stationaryPrev);
  const completeBg = new Map(prevBg);
  for (const [key, color] of currBg) completeBg.set(key, color);
  const same = byId("same-canvas");
  const w = state.result.width, h = state.result.height;
  same.width = w; same.height = h;
  const sbrush = same.getContext("2d");
  sbrush.imageSmoothingEnabled = false;
  sbrush.fillStyle = "#101725"; sbrush.fillRect(0, 0, same.width, same.height);
  for (const [key, color] of completeBg) {
    sbrush.fillStyle = color;
    sbrush.fillRect(key % w, Math.floor(key / w), 1, 1);
  }
  const layer1Source = document.createElement("canvas");
  paintPartsById(layer1Source, state.result, (part) => (movedCurr.has(part.id) ? part.color : null));
  const movedBrush = drawNatural(byId("moved-canvas"), layer1Source);
  drawArrows(movedBrush);
  void ensureLayerPipeline("layer0", byId("same-canvas"));
  void ensureLayerPipeline("layer1", layer1Source);
}

const layerRequests = {};
async function ensureLayerPipeline(prefix, sourceCanvas) {
  const base64 = sourceCanvas.toDataURL("image/png").split(",")[1];
  const token = (layerRequests[prefix] = (layerRequests[prefix] || 0) + 1);
  const label = prefix === "layer0" ? "Layer 0" : "Layer 1";
  try {
    const result = await request("/omega_vision/api/v1/recognize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipeline: byId("pipeline").value === "geometry" ? "opencv" : byId("pipeline").value,
        tolerance: Number(byId("tolerance").value), w_engine: state.wEngine, strong_edge_pct: state.strongEdgePct,
        old_strong_edge_pct: state.oldEdgePct, upscale: state.upscale, crack_angle_tol: state.crackAngleTol,
        frame: { sequenceId: prefix, frameId: `${state.demoFrame?.sequenceId || "bg"}#${state.demoFrame?.frameId || "0"}` },
        image: { base64 },
      }),
    });
    if (token !== layerRequests[prefix] || !result.native) return;
    const [preview, debug] = await Promise.all([decodeDataImage(result.preview), decodeDataImage(result.debug_image)]);
    if (token !== layerRequests[prefix]) return;
    state[`${prefix}Result`] = result;
    state[`${prefix}Preview`] = preview;
    state[`${prefix}Debug`] = debug;
    state[`${prefix}Source`] = sourceCanvas;
    const cell = byId(`${prefix}-companion-cell`);
    const mode = state.companion;
    if (mode === "none" || mode === "original") {
      cell.hidden = true;
    } else {
      const ok = companionDraw(byId(`${prefix}-companion-canvas`), mode,
        { result, preview, debug, parts: null, original: sourceCanvas, overlay: true }, true);
      cell.hidden = !ok;
      if (ok) byId(`${prefix}-companion-tag`).textContent = `${label} companion: ${COMPANION_LABELS[mode]}`;
    }
    renderLayerParts(prefix, label);
    renderLayerGrouping(prefix, label);
  } catch {
    /* transient failure: keep the last good layer content in place rather than hiding it */
  }
}

function renderLayerGrouping(prefix, label) {
  // Read-only group tree for a layer's own recognition result (mirrors Frame Grouping,
  // but without the turtle-selection interaction). Uses the accepted G groups, falling
  // back to W if the layer produced no consensus groups.
  const panel = byId(`${prefix}-grouping`);
  const host = byId(`${prefix}-grouping-host`);
  const result = state[`${prefix}Result`];
  if (!panel || !host) return;
  if (pageMode !== "demos" || !result?.native) { panel.hidden = true; return; }
  const groups = (result.group_layers?.G?.length ? result.group_layers.G : result.group_layers?.W) || [];
  if (!groups.length) { panel.hidden = true; return; }
  panel.hidden = false;
  const objs = new Map((result.objects || []).map((o) => [o.id, o]));
  const parentChildren = new Map();
  for (const [child, parent] of (result.prolog?.child_of || [])) {
    if (!parentChildren.has(parent)) parentChildren.set(parent, []);
    parentChildren.get(parent).push(child);
  }
  const hue = (i) => `hsl(${(i * 47) % 360} 70% 55%)`;
  const sorted = [...groups].sort((a, b) => b.members.length - a.members.length || b.area - a.area);
  const memberSets = new Map(sorted.map((g) => [g, new Set(g.members)]));
  const isSubset = (a, b) => a.members.length < b.members.length && a.members.every((id) => memberSets.get(b).has(id));
  const built = sorted.map((g, i) => {
    const details = document.createElement("details");
    details.open = i === 0;
    const summary = document.createElement("summary");
    summary.append(colorSwatch(hue(i)), document.createTextNode(
      ` ${g.id} \u00b7 ${g.members.length} ${g.members.length === 1 ? "part" : "parts"} \u00b7 ${g.area} px`));
    details.append(summary);
    if (g.reason) {
      const r = document.createElement("p");
      r.className = "group-advisory";
      r.textContent = `accepted: ${String(g.reason).replaceAll("_", " ")}.`;
      details.append(r);
    }
    const kids = [...new Set(g.members.flatMap((id) => parentChildren.get(id) || []))];
    if (kids.length) {
      const k = document.createElement("p");
      k.className = "group-advisory child-note";
      k.textContent = `\u25a3 contains ${kids.length} child glyph${kids.length === 1 ? "" : "s"}: ${kids.sort().join(", ")}.`;
      details.append(k);
    }
    for (const id of g.members) {
      const o = objs.get(id) || {};
      const m = document.createElement("div");
      m.className = "group-member";
      m.append(colorSwatch(o.color || "#8b9db4"), document.createTextNode(`${id} \u00b7 ${o.color || "?"} \u00b7 ${o.area ?? "?"} px`));
      details.append(m);
    }
    return [g, details];
  });
  // Nest strict subsets under their smallest superset, like Frame Grouping.
  const elByGroup = new Map(built.map(([g, el]) => [g, el]));
  const topLevel = [];
  for (const [g, el] of built) {
    let parent = null;
    for (const [cand] of built) {
      if (cand !== g && isSubset(g, cand) && (!parent || cand.members.length < parent.members.length)) parent = cand;
    }
    if (parent && elByGroup.has(parent)) { el.classList.add("nested-node"); elByGroup.get(parent).append(el); }
    else topLevel.push(el);
  }
  host.replaceChildren(...topLevel);
}

function renderLayerParts(prefix, label) {
  const panel = byId(`${prefix}-parts`);
  const result = state[`${prefix}Result`];
  if (pageMode !== "demos" || !result?.native) { panel.hidden = true; return; }
  panel.hidden = false;
  const base = { result, preview: state[`${prefix}Preview`], debug: state[`${prefix}Debug`], original: state[`${prefix}Source`], overlay: true };
  const thumbs = [
    { title: "V groups", mode: "groups", ctx: { ...base, groupsOverride: result.group_layers.V, parts: new Set() } },
    { title: "W groups", mode: "groups", ctx: { ...base, groupsOverride: result.group_layers.W, parts: new Set() } },
    { title: "G groups", mode: "groups", ctx: { ...base, groupsOverride: result.group_layers.G, parts: new Set() } },
    { title: "Turtle", mode: "turtles", ctx: { ...base, parts: new Set() } },
  ];
  byId(`${prefix}-analysis-images`).replaceChildren(...thumbs.map((thumb) => {
    const button = document.createElement("button");
    button.className = "analysis-image";
    button.setAttribute("aria-label", `${label} ${thumb.title}`);
    const title = document.createElement("strong");
    title.textContent = thumb.title;
    const image = document.createElement("canvas");
    image.setAttribute("aria-hidden", "true");
    drawAnalysis(image, thumb.mode, thumb.ctx);
    attachHover(image, () => state[`${prefix}Result`]);
    const caption = document.createElement("small");
    const layer = thumb.title[0];
    caption.textContent = ["V", "W", "G"].includes(layer) ? `${result.group_layers[layer].length} ${layer} groups` : `${result.prolog.turtle_programs.length} turtle programs`;
    button.append(title, image, caption);
    return button;
  }));
  void renderLayerMemory(prefix, label);
}

const layerMemoryRequests = {};
async function renderLayerMemory(prefix, label) {
  // Track this layer as its own memory stream (channel = prefix), so a previous
  // layer0 and the current layer0 are compared over time: what re-appears in the
  // background as occluders move away is read as a reveal, not a brand-new object.
  const panel = byId(`${prefix}-parts`);
  const result = state[`${prefix}Result`];
  if (!panel || !result?.native || !state.demoFrame) return;
  let line = byId(`${prefix}-memory`);
  if (!line) {
    line = document.createElement("p");
    line.id = `${prefix}-memory`;
    line.className = "hint";
    panel.append(line);
  }
  const token = (layerMemoryRequests[prefix] = (layerMemoryRequests[prefix] || 0) + 1);
  const objects = result.objects.map((obj) => ({ id: obj.id, shape_id: obj.shape_id, color: obj.color, area: obj.area, bounds: obj.bounds }));
  try {
    const tracking = await request("/omega_vision/api/v1/track", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sequenceId: state.demoFrame.sequenceId, channel: prefix, order: Number(byId("demo-frame").value),
        width: result.width, height: result.height, objects,
      }),
    });
    if (token !== layerMemoryRequests[prefix]) return;
    const stack = (tracking.layers || []).map((L) => `${L.kind} \u00d7${L.entities.length}`).join("  \u00b7  ");
    line.textContent = `${label} memory: ${tracking.entityCount} entities \u00b7 ${tracking.present.length} present \u00b7 ${tracking.occluded.length} occluded${stack ? " \u2014 " + stack : ""}.`;
  } catch (problem) {
    if (token !== layerMemoryRequests[prefix]) return;
    line.textContent = `${label} memory unavailable: ${problem.message}`;
  }
}

function guideSection(parent, title, lines) {
  if (!lines.length) return;
  const heading = document.createElement("h4");
  heading.textContent = title;
  const list = document.createElement("ul");
  for (const text of lines) {
    const item = document.createElement("li");
    item.textContent = text;
    list.append(item);
  }
  parent.append(heading, list);
}

async function loadFrameGuide(testId, sequenceId, frameId, token) {
  const panel = byId("frame-guide");
  const body = byId("frame-guide-body");
  panel.hidden = false;
  byId("frame-guide-title").textContent = `Expected interpretation \u00b7 frame ${frameId}`;
  body.textContent = "Loading the authored frame description...";
  try {
    const query = new URLSearchParams({ test: testId, sequence: sequenceId, frame: frameId });
    const guide = await request(`/omega_vision/api/v1/demos/expectations?${query}`);
    if (token !== demoRequest) return;
    body.replaceChildren();
    const caption = document.createElement("p");
    caption.textContent = guide.caption || guide.context;
    body.append(caption);
    guideSection(body, "Authored objects in this frame", guide.objects);
    guideSection(body, "Compare with the preceding frame", guide.changes);
    guideSection(body, "Expected interpretation", guide.interpretation);
    const transition = document.createElement("p");
    transition.textContent = guide.transitionNote;
    body.append(transition);
    guideSection(body, "Recorded event targets", guide.events.map((event) => `Frame ${event.fromFrameId} \u2192 ${event.toFrameId}: ${event.description}`));
    guideSection(body, "Conditions for the intended outcome", guide.requirements);
    if (guide.assessment) {
      const assessment = document.createElement("p");
      assessment.textContent = `Authored assessment: ${guide.assessment.replaceAll("_", " ")}.`;
      body.append(assessment);
    }
    const cautions = document.createElement("div");
    cautions.className = "guide-caution";
    guideSection(cautions, "Evidence limits", guide.limitations);
    body.append(cautions);
    if (guide.evidenceSections.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Test memory and timing requirements";
      details.append(summary);
      for (const section of guide.evidenceSections) guideSection(details, section.title, [section.text]);
      body.append(details);
    }
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Authored reference for this frame";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(guide.referenceFrame, null, 2);
    details.append(summary, pre);
    body.append(details);
  } catch (problem) {
    if (token !== demoRequest) return;
    body.textContent = `Expected interpretation unavailable: ${problem.message}. Recognition still uses only the recorded image.`;
  }
}

function selectRecording() {
  const sequence = selectedRecording();
  const available = Boolean(sequence?.frames.length);
  byId("demo-frame-controls").hidden = !available;
  byId("demo-frame").max = String(Math.max(0, (sequence?.frames.length || 0) - 1));
  byId("demo-frame").value = "0";
  void loadLearnedScene();
  void loadInduction();
  if (available) return loadDemoFrame();
  error("This recording has no frames.");
}

let inductionRequest = 0;
async function loadInduction() {
  // Whole-recording inductive guesses shown in the same Interframe tab as the two-frame
  // deductions, using the same stable e# identities. Read from the crawler's
  // induction.json; hidden until the crawler has induced the recording.
  const sub = byId("induction-sub");
  const sequence = selectedRecording();
  if (pageMode !== "demos" || !sequence) { sub.hidden = true; return; }
  const token = ++inductionRequest;
  try {
    const data = await request(`/omega_vision/api/v1/induction?${new URLSearchParams({ sequence: sequence.id })}`);
    if (token !== inductionRequest) return;
    const induction = data.induction || {};
    const body = byId("induction-body");
    body.replaceChildren();
    const line = (strong, rest) => {
      const p = document.createElement("p");
      const b = document.createElement("strong");
      b.textContent = strong;
      p.append(b, ` ${rest}`);
      return p;
    };
    const guesses = induction.guesses || [];
    const statics = guesses.filter((g) => g.kind === "static");
    const constant = guesses.filter((g) => g.kind === "constant_velocity");
    const variable = guesses.filter((g) => g.kind === "variable_motion");
    if (statics.length) {
      body.append(line(`static (${statics.length}):`,
        statics.map((g) => `${g.entity} (${g.support}f)`).join(", ")));
    }
    for (const g of constant) {
      body.append(line("constant velocity:", `${g.entity} moves (${g.dx}, ${g.dy}) px per frame \u00b7 ${g.support} frames`));
    }
    for (const g of variable) {
      body.append(line("variable motion:", `${g.entity} \u00b7 ${g.vectors.length} distinct vectors over ${g.support} frames \u00b7 ` +
        g.vectors.slice(0, 4).map(([dx, dy]) => `(${dx},${dy})`).join(" ") + (g.vectors.length > 4 ? " \u2026" : "")));
    }
    for (const event of induction.recurring || []) {
      body.append(line("recurring event:", `${event.event} \u00d7${event.count}`));
    }
    if (!body.children.length) {
      body.append(line("no inductive guesses yet.", `${induction.transitions ?? 0} transitions examined.`));
    } else {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent = `${guesses.length} guesses from ${induction.transitions ?? "?"} transitions across the whole recording.`;
      body.append(note);
    }
    sub.hidden = false;
    byId("interframe").hidden = false;
  } catch {
    if (token === inductionRequest) sub.hidden = true; // not induced yet; crawler will produce it
  }
}

let sceneRequest = 0;
async function loadLearnedScene() {
  // The whole scene this recording has LEARNED across its frames, composed on the server
  // purely from the crawler's cached recognition artifacts. Darkness only occludes:
  // revealed pixels persist; never-revealed pixels stay dark. Stale caches are reported,
  // never silently recomputed.
  const cell = byId("scene-cell");
  const sequence = selectedRecording();
  if (pageMode !== "demos" || !sequence) { cell.hidden = true; return; }
  const token = ++sceneRequest;
  try {
    const scene = await request(`/omega_vision/api/v1/scene?${new URLSearchParams({ sequence: sequence.id })}`);
    if (token !== sceneRequest) return;
    const image = await decodeDataImage(scene.scene);
    if (token !== sceneRequest) return;
    const canvasEl = byId("scene-canvas");
    const scale = Math.max(1, Math.floor(360 / Math.max(image.width, image.height)));
    canvasEl.width = image.width * scale;
    canvasEl.height = image.height * scale;
    const brush = canvasEl.getContext("2d");
    brush.imageSmoothingEnabled = false;
    brush.drawImage(image, 0, 0, canvasEl.width, canvasEl.height);
    const pct = Math.round(scene.coverage * 100);
    const awaiting = scene.framesAwaitingReprocess?.length ? ` \u00b7 ${scene.framesAwaitingReprocess.length} awaiting reprocess` : "";
    const stale = scene.framesStale.length ? ` \u00b7 ${scene.framesStale.length} frames not cached yet` : "";
    byId("scene-tag").textContent = `Learned scene \u00b7 ${scene.framesUsed.length} frames \u00b7 ${pct}% revealed${awaiting}${stale}`;
    cell.hidden = false;
  } catch {
    if (token === sceneRequest) cell.hidden = true; // no fresh cache yet; the crawler will produce it
  }
}

function renderDemos(catalog) {
  demoCatalog = catalog;
  const select = byId("demo-test");
  select.replaceChildren(new Option("Choose a demo...", ""));
  const groups = new Map();
  let choices = 0;
  const linked = new Set();
  for (const test of demoCatalog.tests) {
    if (!groups.has(test.group)) {
      const group = document.createElement("optgroup");
      group.label = test.group;
      groups.set(test.group, group);
      select.append(group);
    }
    for (const id of test.recordings) {
      const sequence = demoCatalog.sequences.find((item) => item.id === id);
      const option = new Option(demoLabel(test, sequence), JSON.stringify([test.id, sequence.id]));
      option.dataset.testId = test.id;
      option.dataset.sequenceId = sequence.id;
      groups.get(test.group).append(option);
      linked.add(sequence.id);
      choices++;
    }
  }
  // Every recording on disk (recordings/ and curated/) is selectable, even without a
  // linked test: grouped by its directory, labelled with frame count and properties.
  const disk = new Map();
  for (const sequence of demoCatalog.sequences) {
    const folder = sequence.id.split("/").slice(0, -1).join("/");
    const key = linked.has(sequence.id) ? null : folder;
    if (key === null) continue;
    if (!disk.has(key)) {
      const group = document.createElement("optgroup");
      group.label = `All recordings \u2014 ${key}`;
      disk.set(key, group);
      select.append(group);
    }
    const option = new Option(demoLabel(null, sequence), JSON.stringify(["", sequence.id]));
    option.dataset.sequenceId = sequence.id;
    disk.get(key).append(option);
    choices++;
  }
  select.disabled = false;
  byId("demo-description").textContent =
    `${choices} choices: ${demoCatalog.tests.length} authored tests plus every on-disk recording under recordings/ and curated/.`;
}

async function loadDemos() {
  try {
    renderDemos(await request("/omega_vision/api/v1/demos"));
    return true;
  } catch (problem) {
    byId("demo-test").replaceChildren(new Option("Recorded demos unavailable", ""));
    byId("demo-description").textContent = problem.message;
    return false;
  }
}

byId("demo-test").addEventListener("change", () => {
  demoRequest++;
  const choice = selectedDemo();
  if (!choice) {
    clearDemoSelection();
    return;
  }
  byId("demo-description").textContent = choice.test ? choice.test.summary :
    `On-disk recording ${choice.sequence.id} \u00b7 ${sequenceProperties(choice.sequence)}.`;
  selectRecording();
});
byId("demo-frame").addEventListener("change", loadDemoFrame);
byId("demo-frame").addEventListener("input", frameControls);
byId("previous-frame").addEventListener("click", () => {
  byId("demo-frame").value = String(Number(byId("demo-frame").value) - 1);
  loadDemoFrame();
});
byId("next-frame").addEventListener("click", () => {
  byId("demo-frame").value = String(Number(byId("demo-frame").value) + 1);
  loadDemoFrame();
});

byId("recognize").addEventListener("click", recognize);
function pipelineControls() {
  byId("background").disabled = byId("pipeline").value !== "geometry";
  byId("background").title = byId("pipeline").value === "geometry" ? "" : "Native pipelines infer background using Prolog topology rules.";
  byId("tolerance-field").hidden = byId("pipeline").value !== "opencv";
}
byId("pipeline").addEventListener("change", () => {
  invalidate();
  pipelineControls();
  renderGrid();
  requestDemoAnalysis();
});
byId("tolerance").addEventListener("change", () => { invalidate(); renderGrid(); requestDemoAnalysis(); });
byId("w-engine").addEventListener("change", (event) => { state.wEngine = event.target.value; invalidate(); renderGrid(); requestDemoAnalysis(); });
byId("strong-edge-min").addEventListener("change", (event) => {
  const value = Number(event.target.value);
  if (value > 0 && value <= 100) { state.strongEdgePct = value; invalidate(); renderGrid(); requestDemoAnalysis(); }
});
byId("old-edge-pct").addEventListener("change", (event) => {
  const value = Number(event.target.value);
  if (value > 0 && value <= 100) { state.oldEdgePct = value; invalidate(); renderGrid(); requestDemoAnalysis(); }
});
byId("upscale").addEventListener("change", (event) => {
  const value = Number(event.target.value);
  if (Number.isInteger(value) && value >= 1 && value <= 4) { state.upscale = value; invalidate(); renderGrid(); requestDemoAnalysis(); }
});
byId("crack-angle-tol").addEventListener("change", (event) => {
  const value = Number(event.target.value);
  if (value >= 0 && value <= 90) { state.crackAngleTol = value; invalidate(); renderGrid(); requestDemoAnalysis(); }
});
byId("edit-grid").addEventListener("click", () => {
  setView("input");
  state.editing = true;
  state.cursor = [0, 0];
  renderGrid();
  status("Grid editor: painting switches native input from the original image to this edited grid.");
});
byId("example").addEventListener("change", (event) => {
  const example = presets.find((item) => item.id === event.target.value);
  if (!example) return;
  clearDemoSelection();
  loadGrid(example, "Built-in recognition example \u00b7 edit any cell to experiment.");
  byId("example-description").textContent = example.description;
});
byId("background").addEventListener("change", (event) => {
  state.background = event.target.value === "none" ? null : Number(event.target.value);
  invalidate();
  renderGrid();
});
for (const name of ["prev", "input", "regions", "reconstruction"]) {
  const button = byId(`view-${name}`);
  if (button) button.addEventListener("click", () => setView(name));
}
byId("view-groups")?.addEventListener("click", () => { state.analysisMode = "groups"; setView("analysis"); });
byId("show-prev")?.addEventListener("change", () => { renderPrevPair(); void ensurePrevPipeline(); });
byId("clear-companion")?.addEventListener("click", () => setCompanion("none"));
byId("group-preview")?.addEventListener("click", () => setCompanion(state.companion === "selection" ? "none" : "selection"));
attachHover(byId("companion-canvas"), () => state.result);
attachHover(byId("group-preview"), () => state.result);
attachHover(byId("image-canvas"), () => state.result);
attachHover(byId("prev-companion-canvas"), () => state.prevResult);
const overlaySlider = byId("overlay-opacity");
if (overlaySlider) overlaySlider.addEventListener("input", () => {
  state.overlayOpacity = Number(overlaySlider.value) / 100;
  byId("overlay-opacity-val").textContent = `${overlaySlider.value}%`;
  if (state.result?.native) renderFrameAnalysis();
  if (state.view === "analysis") renderGrid();
  renderCompanion();
  renderPrevPair();
});
if (pageMode === "demos") byId("view-input").textContent = "Original";
byId("grid-lines").addEventListener("change", renderGrid);
byId("image-file").addEventListener("change", (event) => importImage(event.target.files[0]));
const zone = byId("drop-zone");
for (const name of ["dragenter", "dragover"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragging"); });
for (const name of ["dragleave", "drop"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("dragging"); });
zone.addEventListener("drop", (event) => importImage(event.dataTransfer.files[0]));
function download(content, name, mediaType) {
  const blob = new Blob([content], { type: mediaType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
byId("download").addEventListener("click", () => {
  if (state.result) download(JSON.stringify(state.result, null, 2) + "\n", "recognition.json", "application/json");
});
byId("download-artifact").addEventListener("click", () => {
  const artifact = state.result?.artifacts?.[Number(byId("artifact").value)];
  if (artifact) download(artifact.content, artifact.name, artifact.media_type);
});
function outputArtifacts() {
  const files = [...(state.result?.artifacts || []), ...(state.deductionFiles || [])];
  if (state.result?.metta && !files.some(file => file.name === state.result.metta.name)) files.push(state.result.metta);
  if (state.result && !files.some(file => file.name === "recognition.json")) {
    files.push({ name: "recognition.json", content: JSON.stringify(state.result, null, 2) + "\n", media_type: "application/json" });
  }
  if (state.twoFrame && state.deductionFiles?.length && !files.some(file => file.name === "deductions.json")) {
    files.push({ name: "deductions.json", content: JSON.stringify(state.twoFrame, null, 2) + "\n", media_type: "application/json" });
  }
  return files;
}
function outputDraftKey(artifact) {
  return JSON.stringify([state.result.frame, state.result.pipeline, artifact.name, artifact.content]);
}

// Prepare the Python-rendered source views, then (re)mount the AtomSpace Explorer as the sole
// output viewer. The explorer owns its own file tabs, predicate tree, syntax selector and editor.
let sourceViewRequest = 0;
function renderOutputEditor() {
  if (!state.result) { renderClauseExplorer(); return; }
  const sources = clauseExplorerSources();
  if (!window.ClauseExplorer.hasSources(sources)) {
    const generation = ++sourceViewRequest;
    void window.ClauseExplorer.prepareSources(sources).then(() => {
      if (generation === sourceViewRequest) renderOutputEditor();
    }).catch(reason => {
      if (generation === sourceViewRequest) error(`Source views: ${reason.message || reason}`);
    });
    return;
  }
  renderClauseExplorer();
}

// Mount the original Workbench explorer; its source editor and tree stay together.
let clauseExplorerInstance = null;
function clauseExplorerSources() {
  return outputArtifacts()
    .filter((a) => /\.(pl|metta|json)$/.test(a.name))
    .map((a) => ({
      name: a.name,
      text: state.outputDrafts.get(outputDraftKey(a)) ?? a.content,
      dialect: a.name.endsWith(".metta") ? "metta" : a.name.endsWith(".pl") ? "prolog" : "json",
      readOnly: !a.name.endsWith(".pl"),
    }));
}
function renderClauseExplorer() {
  const host = byId("clause-explorer");
  if (!host || !window.ClauseExplorer) return;
  if (!state.result) {
    clauseExplorerInstance?.destroy();
    host.replaceChildren();
    clauseExplorerInstance = null;
    return;
  }
  if (!clauseExplorerInstance) {
    clauseExplorerInstance = window.ClauseExplorer.mount(host, {
      getSources: clauseExplorerSources,
      onSourcesChange: (sources) => {
        const updates = sources.filter(source => source.readOnly !== true).map((source) => {
          const artifact = outputArtifacts().find((a) => a.name === source.name);
          if (!artifact || !artifact.name.endsWith(".pl")) throw new Error("Source is no longer available for this frame.");
          return { source, artifact };
        });
        for (const { source, artifact } of updates) {
          const key = outputDraftKey(artifact);
          if (source.text === artifact.content) state.outputDrafts.delete(key);
          else state.outputDrafts.set(key, source.text);
        }
        renderOutputEditor();
      },
    });
  } else {
    clauseExplorerInstance.render();
  }
}


// ---- Section navigation + accordion (UI only; no inference here) ----
const NAV_SECTIONS = [
  ["config-panel", "Config"],
  ["frame-images", "Frame Images"],
  ["frame-analysis", "Frame Parts"],
  ["parts-grouping-panel", "Frame Grouping"],
  ["layer-images", "Layer Images"],
  ["layer0-parts", "Layer0 Parts"],
  ["layer0-grouping", "Layer0 Grouping"],
  ["layer1-parts", "Layer1 Parts"],
  ["layer1-grouping", "Layer1 Grouping"],
  ["interframe", "Interframe"],
  ["frame-metta", "Output"],
  ["frame-guide", "Expected"],
  ["result-json", "Result JSON"],
];
// Desired top-to-bottom order of the in-panel sections (the matrix layout).
const SECTION_ORDER = [
  "frame-images", "frame-analysis", "parts-grouping-panel",
  "layer-images", "layer0-parts", "layer0-grouping",
  "layer1-parts", "layer1-grouping",
  "interframe", "frame-metta", "frame-guide",
];
let accordionSolo = true;
let navInitialized = false;
const pinnedSections = new Set();
// Default left-rail arrangement (top-to-bottom) and sections pinned open on load. These are the
// menu defaults; the user can still drag to reorder or unpin, and their choice then sticks.
const DEFAULT_NAV_ORDER = [
  "frame-metta",          // Output
  "config-panel",         // Config
  "frame-images",         // Frame Images
  "interframe",           // Interframe
  "layer-images",         // Layer Images
  "frame-analysis",       // Frame Parts
  "parts-grouping-panel", // Frame Grouping
  "layer0-parts", "layer0-grouping",
  "layer1-parts", "layer1-grouping",
  "frame-guide",          // Expected
  "result-json",          // Result JSON
];
const DEFAULT_PINS = new Set(["frame-images", "interframe", "layer-images"]);
// Section the left rail highlights (and opens) on startup, before any user interaction.
const DEFAULT_ACTIVE_SECTION = "layer-images";
let defaultActiveApplied = false;
const pinOverrides = new Map();  // id -> explicit user choice, overrides the default
function navDetails() {
  return NAV_SECTIONS.map(([id]) => byId(id)).filter((el) => el && el.tagName === "DETAILS");
}
function collapseOthers(except) {
  if (!accordionSolo) return;
  for (const d of navDetails()) {
    if (d !== except && !d.hidden && d.open && !pinnedSections.has(d.id)) d.open = false;
  }
}
function setActiveNav(id) {
  const nav = byId("section-nav");
  if (!nav) return;
  for (const btn of nav.querySelectorAll(".nav-item")) btn.classList.toggle("active", btn.dataset.target === id);
}
function togglePin(id, on) {
  const nav = byId("section-nav");
  if (on) {
    pinnedSections.add(id);
    const target = byId(id);
    if (target && target.tagName === "DETAILS") target.open = true;  // pinned = kept open
  } else {
    pinnedSections.delete(id);
  }
  if (nav) {
    const pin = nav.querySelector(`.nav-pin[data-target="${id}"]`);
    if (pin) pin.setAttribute("aria-pressed", String(on));
    const item = nav.querySelector(`.nav-item[data-target="${id}"]`);
    if (item) item.classList.toggle("pinned", on);
  }
}
function initSectionNav() {
  const nav = byId("section-nav");
  if (!nav || navInitialized) return;
  navInitialized = true;
  // Put the in-panel sections into the matrix order so the page reads
  // Frame(Images/Parts/Grouping) -> Layer0(...) -> Layer1(...) top to bottom.
  const orderEls = SECTION_ORDER.map((id) => byId(id)).filter(Boolean);
  if (orderEls.length) {
    const parent = orderEls[0].parentNode;
    let ref = orderEls[0];
    for (const el of orderEls) { if (el.parentNode === parent) { parent.insertBefore(el, ref.nextSibling); ref = el; } }
  }
  // Move the grouping section into its own collapsible panel so "Parts" (thumbnails)
  // and "Parts grouping" (group tree + preview) are independent sections.
  const groupingHost = byId("parts-grouping-host");
  const grouping = byId("parts-grouping");
  if (groupingHost && grouping) groupingHost.append(grouping);
  // Per-section image size slider for sections that render (potentially large) images.
  const IMG_SIZE_DEFAULTS = { "frame-images": 200, "layer-images": 200, "interframe": 120 };
  for (const secId of ["frame-images", "layer-images", "interframe"]) {
    const section = byId(secId);
    if (!section || section.querySelector(":scope > .img-size-control")) continue;
    const def = IMG_SIZE_DEFAULTS[secId] || 200;
    const ctl = document.createElement("div");
    ctl.className = "img-size-control";
    const lbl = document.createElement("label");
    lbl.textContent = "Image size";
    const range = document.createElement("input");
    range.type = "range";
    range.min = "120"; range.max = "760"; range.step = "20"; range.value = String(def);
    range.setAttribute("aria-label", "Image size");
    const val = document.createElement("span");
    val.className = "img-size-val";
    val.textContent = `${def}px`;
    range.addEventListener("input", () => {
      section.style.setProperty("--img-max", `${range.value}px`);
      val.textContent = `${range.value}px`;
    });
    lbl.append(range, val);
    ctl.append(lbl);
    section.style.setProperty("--img-max", `${def}px`);
    const summary = section.querySelector(":scope > summary");
    if (summary) summary.after(ctl); else section.prepend(ctl);
  }
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "nav-toggle";
  toggle.setAttribute("aria-pressed", "true");
  toggle.title = "Solo: opening a section collapses the others (pinned ones stay open). Click for Multi.";
  toggle.textContent = "\u25c9 Solo";
  toggle.addEventListener("click", () => {
    accordionSolo = !accordionSolo;
    toggle.setAttribute("aria-pressed", String(accordionSolo));
    toggle.textContent = accordionSolo ? "\u25c9 Solo" : "\u25ce Multi";
    if (accordionSolo) collapseOthers(navDetails().find((d) => !d.hidden && d.open && !pinnedSections.has(d.id)) || null);
  });
  nav.append(toggle);
  // Quick actions in the left rail: previous frame / rerun / next frame.
  const actions = document.createElement("div");
  actions.className = "nav-actions";
  const mkAction = (glyph, title, handlerId) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "nav-action";
    b.textContent = glyph;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", () => byId(handlerId)?.click());
    return b;
  };
  actions.append(
    mkAction("\u2190", "Previous frame", "previous-frame"),
    mkAction("\u21bb", "Rerun recognition", "recognize"),
    mkAction("\u2192", "Next frame", "next-frame"),
  );
  nav.append(actions);
  // Order the menu to follow the sections' actual top-to-bottom order on the page,
  // so the left list always matches what you see on the right.
  const ordered = NAV_SECTIONS.filter(([id]) => byId(id)).sort((a, b) => {
    const ea = byId(a[0]), eb = byId(b[0]);
    return (ea.compareDocumentPosition(eb) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1;
  });
  for (const [id, label] of ordered) {
    const row = document.createElement("div");
    row.className = "nav-row";
    row.dataset.target = id;
    row.hidden = true;
    row.draggable = true;
    const handle = document.createElement("span");
    handle.className = "nav-handle";
    handle.textContent = "\u2807";  // drag affordance
    handle.title = "Drag to reorder";
    row.append(handle);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "nav-item";
    btn.dataset.target = id;
    btn.textContent = label;
    btn.title = label;
    btn.addEventListener("mouseenter", () => byId(id)?.classList.add("nav-target-highlight"));
    btn.addEventListener("mouseleave", () => byId(id)?.classList.remove("nav-target-highlight"));
    btn.addEventListener("click", () => {
      defaultActiveApplied = true;  // user took over; stop auto-selecting the default section
      const target = byId(id);
      if (!target) return;
      if (target.tagName === "DETAILS") {
        // Toggle: clicking an already-open section collapses it; otherwise open it
        // (and, in Solo mode, collapse the others).
        target.open = !target.open;
        if (target.open) { collapseOthers(target); setActiveNav(id); target.scrollIntoView({ behavior: "smooth", block: "start" }); }
        else if (byId("section-nav")) byId("section-nav").querySelector(`.nav-item[data-target="${id}"]`)?.classList.remove("active");
      } else {
        setActiveNav(id);
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    row.append(btn);
    // Only collapsible (details) sections can be pinned open; the frame viewer just scrolls.
    if (byId(id)?.tagName === "DETAILS") {
      const pin = document.createElement("button");
      pin.type = "button";
      pin.className = "nav-pin";
      pin.dataset.target = id;
      pin.setAttribute("aria-pressed", "false");
      pin.title = "Pin this section open (keeps it open while you solo others)";
      pin.textContent = "\u{1F4CC}";
      pin.addEventListener("click", (event) => {
        event.stopPropagation();
        defaultActiveApplied = true;  // user took over the rail
        const on = !pinnedSections.has(id);
        pinOverrides.set(id, on);  // remember the user's explicit choice so it sticks
        togglePin(id, on);
      });
      row.append(pin);
    }
    // Drag to reorder: move the nav row, then reorder the page sections to match.
    row.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", id);
      event.dataTransfer.effectAllowed = "move";
      row.classList.add("dragging");
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      nav.querySelectorAll(".nav-row").forEach((r) => r.classList.remove("drop-above", "drop-below"));
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const rect = row.getBoundingClientRect();
      const after = event.clientY > rect.top + rect.height / 2;
      row.classList.toggle("drop-below", after);
      row.classList.toggle("drop-above", !after);
    });
    row.addEventListener("dragleave", () => row.classList.remove("drop-above", "drop-below"));
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      const draggedId = event.dataTransfer.getData("text/plain");
      const dragged = nav.querySelector(`.nav-row[data-target="${draggedId}"]`);
      row.classList.remove("drop-above", "drop-below");
      if (!dragged || dragged === row) return;
      const rect = row.getBoundingClientRect();
      const after = event.clientY > rect.top + rect.height / 2;
      nav.insertBefore(dragged, after ? row.nextSibling : row);
      syncSectionOrderToNav();
    });
    nav.append(row);
  }
  for (const d of navDetails()) {
    d.addEventListener("toggle", () => { if (d.open) { collapseOthers(d); setActiveNav(d.id); } });
  }
  // Put the left rail into the default arrangement (user drags override this afterward).
  applyDefaultNavOrder();
  // Keep the enabled/dimmed state in sync whenever any section is shown/hidden
  // asynchronously (deduction, layer pipelines, two-frame, guide, etc.).
  const observer = new MutationObserver(() => refreshSectionNav());
  for (const [id] of NAV_SECTIONS) {
    const target = byId(id);
    if (target) observer.observe(target, { attributes: true, attributeFilter: ["hidden"] });
  }
  refreshSectionNav();
}
function syncSectionOrderToNav() {
  // Reorder the actual page sections to match the nav row order. Sections that share a
  // parent (the image panel) are reordered among themselves; sections in other parents
  // (Config, Result JSON) keep their place.
  const nav = byId("section-nav");
  if (!nav) return;
  const ids = [...nav.querySelectorAll(".nav-row")].map((r) => r.dataset.target);
  const byParent = new Map();
  for (const id of ids) {
    const el = byId(id);
    if (!el) continue;
    if (!byParent.has(el.parentNode)) byParent.set(el.parentNode, []);
    byParent.get(el.parentNode).push(el);
  }
  for (const [parent, group] of byParent) {
    let ref = group[0];
    for (const el of group) { parent.insertBefore(el, ref.nextSibling); ref = el; }
  }
}
function applyDefaultNavOrder() {
  const nav = byId("section-nav");
  if (!nav) return;
  const rows = new Map([...nav.querySelectorAll(".nav-row")].map((r) => [r.dataset.target, r]));
  for (const id of DEFAULT_NAV_ORDER) {
    const row = rows.get(id);
    if (row) nav.append(row);  // append in default order; unlisted rows keep their relative place
  }
  syncSectionOrderToNav();
}
function refreshSectionNav() {
  const nav = byId("section-nav");
  if (!nav) return;
  for (const row of nav.querySelectorAll(".nav-row")) {
    const id = row.dataset.target;
    const target = byId(id);
    // Always list every section; dim (disable) the ones whose data isn't ready yet
    // rather than hiding them, so the menu shows the full set of collapsible parts.
    if (!target) { row.hidden = true; continue; }
    row.hidden = false;
    const ready = !target.hidden;
    const item = row.querySelector(".nav-item");
    const pin = row.querySelector(".nav-pin");
    if (item) { item.disabled = !ready; item.classList.toggle("unavailable", !ready); }
    if (pin) pin.disabled = !ready;
    if (!ready) { pinnedSections.delete(id); continue; }
    // Apply the sticky pin state once a section is ready: the user's explicit choice wins,
    // otherwise fall back to the menu default. This re-pins defaults as data loads in.
    if (pin) {
      const desired = pinOverrides.has(id) ? pinOverrides.get(id) : DEFAULT_PINS.has(id);
      if (desired !== pinnedSections.has(id)) togglePin(id, desired);
    }
  }
  // On startup (before the user touches the rail), highlight and open the default section.
  if (!defaultActiveApplied) {
    const target = byId(DEFAULT_ACTIVE_SECTION);
    if (target && !target.hidden) {
      if (target.tagName === "DETAILS") target.open = true;
      setActiveNav(DEFAULT_ACTIVE_SECTION);
      defaultActiveApplied = true;
    }
  }
}

(async () => {
  try {
    initSectionNav();
    const availability = await request("/omega_vision/api/v1/capabilities");
    byId("pipeline-availability").textContent = `OpenCV: ${availability.opencv ? "available" : "missing dependencies"}. SWI-Prolog: ${availability.prolog ? "available" : "not on PATH"}. Failures are reported, not replaced with geometry-only results.`;
    pipelineControls();
    if (pageMode === "demos") {
      byId("pipeline").querySelector('option[value="geometry"]').remove();
      canvas.setAttribute("aria-label", "Original recorded demo frame. Use the frame controls to navigate.");
      if (!await loadDemos()) {
        status("Recorded demo data is unavailable. Configure --data-root, or open Shapes for independent image recognition.");
        return;
      }
      const query = new URLSearchParams(location.search);
      const requested = JSON.stringify([query.get("test"), query.get("recording")]);
      const select = byId("demo-test");
      const option = [...select.options].find((item) => item.value === requested)
        || [...select.options].find((item) => item.dataset.sequenceId === query.get("recording"))
        || select.options[1];
      if (!option) {
        status("No test-recording links are available in this catalogue.");
        return;
      }
      select.value = option.value;
      const choice = selectedDemo();
      byId("demo-description").textContent = choice.test ? choice.test.summary :
        `On-disk recording ${choice.sequence.id} \u00b7 ${sequenceProperties(choice.sequence)}.`;
      byId("demo-frame-controls").hidden = false;
      byId("demo-frame").max = String(choice.sequence.frames.length - 1);
      const index = choice.sequence.frames.findIndex((frame) => frame.frameId === query.get("frame"));
      byId("demo-frame").value = String(Math.max(0, index));
      void loadLearnedScene();
      void loadInduction();
      await loadDemoFrame();
    } else {
      document.title = "Shape explorer";
      byId("page-eyebrow").textContent = "OMEGA VISION / SHAPE EXPLORER";
      byId("page-title").textContent = "Explore shapes in an image.";
      byId("page-description").textContent = "Upload an image, draw a grid, or try a quick shape example.";
      byId("image-heading").textContent = "Analysis grid";
      byId("recognize-label").textContent = "Recognize shapes";
      presets = await request("/omega_vision/api/v1/examples");
      byId("example").replaceChildren(...presets.map((item) => new Option(item.title, item.id)));
      byId("example").disabled = false;
      loadGrid(presets[0], "Original Omega Vision grid example \u00b7 edit any cell to experiment.");
      byId("example-description").textContent = presets[0].description;
      await recognize();
    }
  } catch (problem) {
    error(problem.message);
    status("Could not reach the local app. Start app.py and reload.");
  }
})();
