/* Draft ReFormat — browser-side editor. */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const kindNames = {
  text: "文字段落", image: "图片 / 插图", table: "表格", chemistry: "化学结构式",
  biology: "生物图片", formula: "数学公式", other: "其他内容"
};
const kindShort = { text: "TEXT", image: "IMAGE", table: "TABLE", chemistry: "CHEM", biology: "BIO", formula: "FORMULA", other: "BLOCK" };
const kindColors = { text: "#ac8cff", image: "#61d7d4", table: "#63d7aa", chemistry: "#eec77a", biology: "#61d7d4", formula: "#eec77a", other: "#9aa3b4" };
const demoRegions = [
  { id: "demo-1", label: "章节标题", kind: "text", x: 8, y: 6, w: 84, h: 12, confidence: .96, group: "A", description: "主标题与题目范围" },
  { id: "demo-2", label: "题干与说明", kind: "text", x: 8, y: 22, w: 84, h: 21, confidence: .91, group: "A", description: "连续正文段落，建议保持完整" },
  { id: "demo-3", label: "生物图片", kind: "biology", x: 9, y: 49, w: 39, h: 30, confidence: .87, group: "B", description: "带标注的生物示意图" },
  { id: "demo-4", label: "化学结构式", kind: "chemistry", x: 53, y: 51, w: 37, h: 24, confidence: .82, group: "B", description: "化学结构式，避免从键线中间切断" },
  { id: "demo-5", label: "图注", kind: "text", x: 53, y: 78, w: 37, h: 8, confidence: .8, group: "B", description: "与右侧图片关联的图注" }
];

const state = {
  projectName: "未命名草稿",
  images: [],
  currentId: null,
  selectedRegionId: null,
  tool: "select",
  zoom: 1,
  history: [],
  redo: [],
  paintPaths: {},
  whiteRects: {},
  layoutWhiteRects: [],
  layoutPaintPaths: [],
  hydrating: false,
  lastAnalyzed: null,
  lastSupervision: null,
  keepGroups: true,
};

function demoImage() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="920" height="1160" viewBox="0 0 920 1160">
    <rect width="920" height="1160" fill="#f5f2eb"/><rect x="38" y="38" width="844" height="1084" rx="5" fill="#fffdf9" stroke="#d6d0c5" stroke-width="2"/>
    <text x="82" y="126" font-size="28" font-family="Georgia,serif" fill="#2f3340">生物与化学综合练习</text><text x="82" y="166" font-size="15" font-family="Arial" fill="#676b75">请阅读材料，完成下列问题。图中标注和结构式应保持完整。</text>
    <line x1="82" y1="195" x2="838" y2="195" stroke="#ded9d0"/>
    <text x="82" y="250" font-size="17" font-family="Arial" fill="#424652">1. 观察下图，判断细胞结构与物质运输方向。</text>
    <text x="82" y="286" font-size="14" font-family="Arial" fill="#777b84">某研究小组在显微镜下记录了不同处理条件下的变化，结果如图所示：</text>
    <rect x="98" y="352" width="330" height="280" rx="4" fill="#edf5f2" stroke="#bed7cf"/><ellipse cx="262" cy="492" rx="126" ry="86" fill="#d3eae1" stroke="#558e79" stroke-width="3"/><ellipse cx="264" cy="489" rx="46" ry="32" fill="#94c4b1" stroke="#447b69" stroke-width="2"/><circle cx="185" cy="442" r="13" fill="#80b39f"/><circle cx="342" cy="520" r="13" fill="#80b39f"/><path d="M160 520 Q260 410 360 535 M200 405 Q282 485 345 576" fill="none" stroke="#5d9a83" stroke-width="3"/><text x="116" y="613" font-size="14" font-family="Arial" fill="#537466">图 1  细胞结构示意图</text>
    <text x="490" y="388" font-size="16" font-family="Arial" fill="#454a56">2. 下列化合物参与反应：</text><text x="528" y="445" font-size="23" font-family="Georgia,serif" fill="#343844">H₃C—CH₂—OH</text><path d="M510 490 h60 m28 0 h60 m28 0 h60" stroke="#6e7480" stroke-width="2"/><text x="520" y="545" font-size="17" font-family="Arial" fill="#454a56">→  CH₃CHO  +  H₂O</text><text x="493" y="598" font-size="13" font-family="Arial" fill="#7b808b">图 2  化学结构式与反应关系</text>
    <line x1="82" y1="700" x2="838" y2="700" stroke="#e1ddd4"/><text x="82" y="756" font-size="16" font-family="Arial" fill="#454a56">3. 请结合材料，解释图 1 中现象并写出结论。</text><line x1="82" y1="800" x2="835" y2="800" stroke="#d5d0c7"/><line x1="82" y1="840" x2="835" y2="840" stroke="#d5d0c7"/><line x1="82" y1="880" x2="835" y2="880" stroke="#d5d0c7"/><text x="82" y="1020" font-size="12" font-family="Arial" fill="#999b9f">Draft ReFormat demo page · 2026</text>
  </svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function makeImage(name, src, extra = {}) {
  return { id: `img-${Date.now()}-${Math.random().toString(16).slice(2)}`, name, src, regions: [], ...extra };
}

function init() {
  const demo = makeImage("biology_chemistry_draft.png", demoImage(), { size: "1.2 MB", regions: structuredClone(demoRegions), analyzed: true });
  const demo2 = makeImage("question_set_02.jpg", demoImage(), { size: "0.8 MB", regions: [], analyzed: false });
  state.images = [demo, demo2];
  state.currentId = demo.id;
  state.selectedRegionId = demoRegions[1].id;
  bindEvents();
  render();
  showToast("已加载演示草稿，可直接拖动分区开始编辑", "success");
}

function currentImage() { return state.images.find((image) => image.id === state.currentId) || null; }
function selectedRegion() { const image = currentImage(); return image?.regions.find((region) => region.id === state.selectedRegionId) || null; }
function snapshot() { return JSON.stringify({ images: state.images, currentId: state.currentId, selectedRegionId: state.selectedRegionId, paintPaths: state.paintPaths, whiteRects: state.whiteRects, layoutWhiteRects: state.layoutWhiteRects, layoutPaintPaths: state.layoutPaintPaths }); }
function restoreSnapshot(value) { const parsed = JSON.parse(value); state.images = parsed.images; state.currentId = parsed.currentId; state.selectedRegionId = parsed.selectedRegionId; state.paintPaths = parsed.paintPaths || {}; state.whiteRects = parsed.whiteRects || {}; state.layoutWhiteRects = parsed.layoutWhiteRects || []; state.layoutPaintPaths = parsed.layoutPaintPaths || []; render(); }
function pushHistory() {
  const image = currentImage();
  if (image?.supervisionPending && !image.applyingSupervision) image.supervisionUserEdited = true;
  state.history.push(snapshot()); if (state.history.length > 35) state.history.shift(); state.redo = [];
}
function undo() { if (!state.history.length) return showToast("没有可撤销的操作", "warn"); state.redo.push(snapshot()); restoreSnapshot(state.history.pop()); }
function redo() { if (!state.redo.length) return showToast("没有可重做的操作", "warn"); state.history.push(snapshot()); restoreSnapshot(state.redo.pop()); }

function render() {
  $("#projectName").textContent = state.projectName;
  $("#imageCount").textContent = state.images.length;
  renderAssets();
  const image = currentImage();
  $("#emptyState").hidden = !!image;
  $("#canvasWrap").hidden = !image;
  if (!image) { $("#currentImageName").textContent = "未选择图片"; $("#regionCount").textContent = "0 个内容块"; $("#groupCount").textContent = "0 个编号集合"; renderInspector(); return; }
  $("#currentImageName").textContent = image.name;
  renderRegions();
  renderInspector();
  renderStats();
  applyZoom();
  setToolVisuals();
  resizePaintCanvas(); drawPaint();
}

function renderAssets() {
  const list = $("#assetList");
  if (!state.images.length) { list.innerHTML = '<div class="empty-assets">还没有导入素材</div>'; return; }
  list.innerHTML = state.images.map((image, index) => `<div class="asset-item ${image.id === state.currentId ? "active" : ""}" data-image-id="${image.id}">
    <img class="asset-thumb" src="${image.src}" alt=""/><div class="asset-info"><div class="asset-name">${escapeHtml(image.name)}</div><div class="asset-meta"><i></i>${image.regions.length ? `${image.regions.length} 个内容块` : "待分析"}<span>·</span>${image.size || "网页素材"}</div></div><span class="asset-index">${String(index + 1).padStart(2, "0")}</span><button class="asset-delete" data-delete-image="${image.id}" title="删除素材">×</button></div>`).join("");
  $$(".asset-item").forEach((item) => item.addEventListener("click", () => { state.currentId = item.dataset.imageId; state.selectedRegionId = currentImage()?.regions[0]?.id || null; render(); }));
  $$("[data-delete-image]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); deleteImage(button.dataset.deleteImage); }));
}

function renderRegions() {
  const layer = $("#regionLayer");
  const items = visualRegions();
  layer.innerHTML = `${state.layoutWhiteRects.map((rect) => `<div class="layout-whiteout" style="left:${rect.x}px;top:${rect.y}px;width:${rect.w}px;height:${rect.h}px"></div>`).join("")}${items.map(({ image, region }) => `<div class="region-tile ${region.id === state.selectedRegionId && image.id === state.currentId ? "selected" : ""}" data-region-id="${region.id}" data-image-id="${image.id}" data-kind="${region.kind}" style="left:${region.layoutX || 28}px;top:${region.layoutY || 28}px;width:${region.layoutW || 240}px;height:${region.layoutH || 120}px;border-color:${kindColors[region.kind] || kindColors.other};z-index:${region.zIndex || 2}">
    <img src="${region.cropSrc || image.src}" alt="${escapeHtml(region.label)}" draggable="false"/><div class="tile-label"><span>${escapeHtml(region.label)}</span><i>${escapeHtml(region.group || "—")}</i></div><span class="tile-kind">${kindShort[region.kind] || "BLOCK"}</span><button class="tile-delete" data-delete-region="${region.id}" title="删除内容块">×</button></div>`).join("")}`;
  $$(".region-tile").forEach((box) => {
    box.addEventListener("pointerdown", (event) => startRegionPointer(event, box));
    box.addEventListener("click", (event) => { event.stopPropagation(); state.currentId = box.dataset.imageId; state.selectedRegionId = box.dataset.regionId; renderRegions(); renderInspector(); });
  });
  $$("[data-delete-region]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); deleteRegion(button.closest(".region-tile").dataset.imageId, button.dataset.deleteRegion); }));
  updateOutputCanvasSize(items);
  if (!state.hydrating && items.some(({ region, image }) => !region.cropSrc && (!region.synthetic || !image.previewReady))) hydrateVisualRegions();
}

function visualRegions() {
  const result = [];
  state.images.forEach((image) => {
    if (!image.regions.length && !image.syntheticRegion) image.syntheticRegion = { id: `whole-${image.id}`, label: image.name, kind: "other", x: 0, y: 0, w: 100, h: 100, confidence: 1, group: "—", description: "尚未分析的整张图片", synthetic: true, layoutW: 740, layoutH: 300, layoutX: 28, layoutY: 28 };
    const regions = image.regions.length ? image.regions : [image.syntheticRegion];
    regions.forEach((region) => result.push({ image, region }));
  });
  return result;
}

function updateOutputCanvasSize(items) {
  const canvas = $("#outputCanvas"); if (!canvas) return;
  const bottom = items.reduce((max, item) => Math.max(max, (item.region.layoutY || 28) + (item.region.layoutH || 120)), 0);
  canvas.style.height = `${Math.max(1120, bottom + 44)}px`;
  canvas.style.minHeight = `${Math.max(1120, bottom + 44)}px`;
}

async function hydrateVisualRegions() {
  state.hydrating = true;
  try {
    const items = visualRegions();
    for (const { image, region } of items) {
      if (!image.aspect) image.aspect = await imageAspect(image.src);
      if (region.synthetic) { region.layoutW = 740; region.layoutH = Math.round(740 / (image.aspect || .72)); }
      else if (!region.layoutW || !region.layoutH) initializeRegionLayout(region, image);
      if (!region.cropSrc && !region.synthetic) region.cropSrc = await cropRegion(image, region);
      if (region.synthetic && !region.cropSrc) { region.cropSrc = image.src; image.previewReady = true; }
    }
    normalizeLongLayout();
  } finally {
    state.hydrating = false;
    renderRegions();
    resizePaintCanvas(); drawPaint();
  }
}

function imageAspect(src) { return new Promise((resolve) => { const img = new Image(); img.onload = () => resolve(img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : .72); img.onerror = () => resolve(.72); img.src = src; }); }

function initializeRegionLayout(region, image) {
  const width = Math.max(150, Math.min(760, 760 * region.w / 100));
  region.layoutW = Math.round(width);
  // The crop's aspect is (sourceAspect * w%) / h%; with a tile width of
  // baseWidth * w%, the matching height is baseWidth * h% / sourceAspect.
  region.layoutH = Math.round(Math.max(54, 760 * region.h / 100 / (image.aspect || .72)));
  region.layoutX = 28;
  const all = visualRegions().filter(({ region: item }) => item !== region && item.layoutY != null);
  const last = all.reduce((max, item) => Math.max(max, item.region.layoutY + item.region.layoutH), 30);
  region.layoutY = last + 24;
}

function normalizeLongLayout() {
  let y = 28;
  state.images.forEach((image) => {
    const regions = image.regions.length ? image.regions : [image.syntheticRegion];
    regions.forEach((region) => {
      if (!region.layoutW || !region.layoutH) initializeRegionLayout(region, image);
      if (!region.userMoved) { region.layoutX = 28; region.layoutY = y; }
      y = Math.max(y, region.layoutY + region.layoutH + 24);
    });
    y += 20;
  });
}

function renderStats() {
  const image = currentImage();
  const regions = state.images.flatMap((item) => item.regions || []);
  const groups = new Set(regions.map((r) => r.group).filter(Boolean));
  $("#regionCount").textContent = `${regions.length} 个内容块`;
  $("#groupCount").textContent = `${groups.size} 个编号集合`;
  $("#lastAnalyzed").textContent = image?.analyzed ? (state.lastAnalyzed || "刚刚") : "尚未分析";
}

function renderInspector() {
  const region = selectedRegion();
  $("#noSelection").hidden = !!region;
  $("#regionInspector").hidden = !region;
  if (!region) return;
  $("#previewType").textContent = kindShort[region.kind] || "BLOCK";
  $("#previewGroup").textContent = `集合 ${region.group || "—"}`;
  $("#regionLabel").value = region.label;
  $("#regionKind").textContent = kindNames[region.kind] || kindNames.other;
  $("#regionGroup").value = region.group || "";
  $("#groupBadge").textContent = region.group || "—";
  $("#regionX").value = region.x; $("#regionY").value = region.y; $("#regionW").value = region.w; $("#regionH").value = region.h;
  const confidence = Math.round((region.confidence || .6) * 100); $("#confidenceValue").textContent = `${confidence}%`; $("#confidenceBar").style.width = `${confidence}%`; $("#regionDescription").textContent = region.description || "语义内容区域";
}

function bindEvents() {
  $("#fileInput").addEventListener("change", (event) => handleFiles([...event.target.files]));
  $("#htmlInput").addEventListener("change", (event) => handleHtmlFiles([...event.target.files]));
  $("#segmentButton").addEventListener("click", segmentCurrent);
  $("#segmentAllButton").addEventListener("click", segmentAll);
  $("#importUrlButton").addEventListener("click", importWebpage);
  $("#urlInput").addEventListener("keydown", (event) => { if (event.key === "Enter") importWebpage(); });
  $("#undoButton").addEventListener("click", undo); $("#redoButton").addEventListener("click", redo);
  $("#zoomOut").addEventListener("click", () => { state.zoom = Math.max(.65, +(state.zoom - .1).toFixed(2)); applyZoom(); });
  $("#zoomIn").addEventListener("click", () => { state.zoom = Math.min(1.6, +(state.zoom + .1).toFixed(2)); applyZoom(); });
  $("#fitButton").addEventListener("click", () => { state.zoom = 1; applyZoom(); });
  $("#saveProjectButton").addEventListener("click", saveProject);
  $("#exportButton").addEventListener("click", exportFinal); $("#inspectorExport").addEventListener("click", exportFinal);
  $("#deleteRegion").addEventListener("click", deleteSelected); $("#removeInspectorRegion").addEventListener("click", deleteSelected);
  $("#clearWhiteouts").addEventListener("click", clearWhiteouts);
  $("#renameProject").addEventListener("click", () => { const name = prompt("项目名称", state.projectName); if (name?.trim()) { state.projectName = name.trim(); render(); } });
  $("#sortImages").addEventListener("click", () => { pushHistory(); state.images.sort((a, b) => a.name.localeCompare(b.name, "zh")); render(); showToast("已按文件名排序", "success"); });
  $("#kindSelect").addEventListener("click", () => $("#kindMenu").classList.toggle("open"));
  $$("#kindMenu button").forEach((button) => button.addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.kind = button.dataset.kind; render(); }));
  $$(".suggestion-row button").forEach((button) => button.addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.label = button.dataset.label; render(); }));
  $("#regionLabel").addEventListener("change", (event) => updateSelected("label", event.target.value));
  $("#regionGroup").addEventListener("change", (event) => updateSelected("group", event.target.value || "A"));
  $("#newGroupButton").addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.group = nextGroup(); render(); });
  ["X", "Y", "W", "H"].forEach((key) => $("#region" + key).addEventListener("change", (event) => updateSelected(key.toLowerCase(), Number(event.target.value))));
  $("#layerBottom").addEventListener("click", () => changeLayer("bottom")); $("#layerDown").addEventListener("click", () => changeLayer("down")); $("#layerUp").addEventListener("click", () => changeLayer("up")); $("#layerTop").addEventListener("click", () => changeLayer("top"));
  $("#keepGroupsToggle").addEventListener("click", () => { state.keepGroups = !state.keepGroups; $("#keepGroupsToggle").classList.toggle("on", state.keepGroups); });
  $("#marginRange").addEventListener("input", (event) => { $("#marginValue").textContent = `${event.target.value} px`; });
  $$(".tool-button").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.tool)));
  const frame = $("#canvasFrame");
  frame.addEventListener("pointerdown", startCanvasPointer);
  $("#paintLayer").addEventListener("pointerdown", startBrushStroke);
  document.addEventListener("keydown", (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); } if (event.key === "Escape") { setTool("select"); $("#kindMenu").classList.remove("open"); } });
  window.addEventListener("resize", () => { resizePaintCanvas(); drawPaint(); });
  $("#canvasArea").addEventListener("wheel", (event) => { if (Math.abs(event.deltaY) > 0) { event.preventDefault(); $("#canvasArea").scrollTop += event.deltaY; } }, { passive: false });
}

function setTool(tool) { state.tool = tool; setToolVisuals(); $("#canvasFrame").classList.toggle("painting", tool === "brush"); }
function setToolVisuals() { $$(".tool-button").forEach((button) => button.classList.toggle("active", button.dataset.tool === state.tool)); const name = { select: "选择", draw: "分区", brush: "涂白", cover: "覆盖" }[state.tool]; $("#toolHint").textContent = name; }
function applyZoom() { $("#zoomLabel").textContent = `${Math.round(state.zoom * 100)}%`; const canvas = $("#outputCanvas"); if (canvas) canvas.style.zoom = state.zoom; $("#canvasWrap").style.width = "820px"; }

function startRegionPointer(event, box) {
  if (state.tool !== "select") return;
  event.stopPropagation(); event.preventDefault();
  const image = state.images.find((item) => item.id === box.dataset.imageId); const region = image?.regions.find((item) => item.id === box.dataset.regionId); if (!region) return;
  state.currentId = image.id; state.selectedRegionId = region.id; renderInspector(); renderRegions();
  const canvasRect = $("#outputCanvas").getBoundingClientRect(); const sx = event.clientX; const sy = event.clientY; const original = { x: region.layoutX || 28, y: region.layoutY || 28 };
  const scale = state.zoom || 1;
  const move = (moveEvent) => { const dx = (moveEvent.clientX - sx) / scale; const dy = (moveEvent.clientY - sy) / scale; region.layoutX = clamp(original.x + dx, 8, Math.max(8, 800 - (region.layoutW || 160))); region.layoutY = Math.max(8, original.y + dy); region.userMoved = true; renderRegions(); renderInspector(); };
  const up = () => { pushHistory(); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function startCanvasPointer(event) {
  if (event.target.closest(".region-box, .region-tile") || !currentImage()) return;
  const canvasRect = $("#outputCanvas").getBoundingClientRect(); const start = canvasPoint(event.clientX, event.clientY, canvasRect);
  if (state.tool === "draw" || state.tool === "cover") {
    event.preventDefault(); let preview;
    if (state.tool === "draw") { preview = document.createElement("div"); preview.className = "region-box selected"; preview.style.cssText = `left:${start.x}px;top:${start.y}px;width:0;height:0;border-style:dashed`; $("#regionLayer").appendChild(preview); }
    else { preview = document.createElement("div"); preview.style.cssText = `position:absolute;left:${start.x}px;top:${start.y}px;width:0;height:0;background:rgba(255,255,255,.8);z-index:4`; $("#regionLayer").appendChild(preview); }
    const move = (moveEvent) => { const now = canvasPoint(moveEvent.clientX, moveEvent.clientY, canvasRect); const box = rectFromPoints(start, now); preview.style.left = `${box.x}px`; preview.style.top = `${box.y}px`; preview.style.width = `${box.w}px`; preview.style.height = `${box.h}px`; };
    const up = (upEvent) => { const now = canvasPoint(upEvent.clientX, upEvent.clientY, canvasRect); const box = rectFromPoints(start, now); preview.remove(); if (box.w > 8 && box.h > 8) { pushHistory(); if (state.tool === "draw") { const source = currentImage(); const region = { id: `manual-${Date.now()}`, label: "手动分区", kind: "other", x: box.x / 760 * 100, y: 0, w: box.w / 760 * 100, h: 20, confidence: 1, group: nextGroup(), description: "人工创建的裁剪区域", layoutX: box.x, layoutY: box.y, layoutW: box.w, layoutH: box.h, userMoved: true }; source.regions.push(region); state.selectedRegionId = region.id; region.cropSrc = null; } else { state.layoutWhiteRects.push(box); } render(); } window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
  }
}

function startBrushStroke(event) {
  if (state.tool !== "brush" || !currentImage()) return;
  event.preventDefault();
  const rect = $("#outputCanvas").getBoundingClientRect();
  const path = { size: 8, points: [canvasPoint(event.clientX, event.clientY, rect)] };
  state.layoutPaintPaths.push(path);
  const move = (moveEvent) => { path.points.push(canvasPoint(moveEvent.clientX, moveEvent.clientY, rect)); drawPaint(); };
  const up = () => { pushHistory(); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function canvasPoint(clientX, clientY, rect) { const scale = state.zoom || 1; return { x: Math.max(0, (clientX - rect.left) / scale), y: Math.max(0, (clientY - rect.top) / scale) }; }
function normPoint(clientX, clientY, rect) { return { x: clamp((clientX - rect.left) / rect.width * 100, 0, 100), y: clamp((clientY - rect.top) / rect.height * 100, 0, 100) }; }
function rectFromPoints(a, b) { return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) }; }
function clamp(value, min, max) { return Math.max(min, Math.min(max, Number(value) || 0)); }
function nextGroup() { const groups = new Set((currentImage()?.regions || []).map((region) => region.group)); let n = 1; while (groups.has(String.fromCharCode(64 + n))) n++; return String.fromCharCode(64 + n); }
function updateSelected(key, value) { const region = selectedRegion(); if (!region) return; pushHistory(); if (["x", "y", "w", "h"].includes(key)) value = clamp(value, key === "w" || key === "h" ? 1 : 0, 100); region[key] = value; if (key === "x") region.w = Math.min(region.w, 100 - value); if (key === "y") region.h = Math.min(region.h, 100 - value); if (["x", "y", "w", "h"].includes(key)) region.cropSrc = null; render(); }
function changeLayer(direction) { const image = currentImage(); const region = selectedRegion(); if (!image || !region) return showToast("请先选择一个内容块", "warn"); pushHistory(); const regions = image.regions; const index = regions.findIndex((item) => item.id === region.id); if (index < 0) return; const target = direction === "top" ? regions.length - 1 : direction === "bottom" ? 0 : direction === "up" ? Math.min(regions.length - 1, index + 1) : Math.max(0, index - 1); if (target !== index) { regions.splice(index, 1); regions.splice(target, 0, region); } regions.forEach((item, order) => { item.zIndex = order + 2; }); render(); showToast(direction === "top" ? "已置于顶层" : direction === "bottom" ? "已置于底层" : direction === "up" ? "已上移一层" : "已下移一层", "success"); }

async function handleFiles(files) {
  if (!files.length) return;
  for (const file of files) { const src = await fileToDataUrl(file); state.images.push(makeImage(file.name, src, { size: formatBytes(file.size) })); }
  if (!state.currentId) state.currentId = state.images[0].id; render(); showToast(`已加入 ${files.length} 张图片`, "success");
}
async function handleHtmlFiles(files) {
  for (const file of files) {
    const html = await file.text();
    const title = (html.match(/<title[^>]*>(.*?)<\/title>/is)?.[1] || file.name).replace(/\s+/g, " ").trim();
    const sources = [...html.matchAll(/<(?:img|source)[^>]+(?:src|srcset)=["']([^"']+)["']/gi)].map((match) => match[1].split(/\s+/)[0]).filter(Boolean);
    const imageItems = await Promise.all(sources.slice(0, 6).map(async (src, index) => {
      if (src.startsWith("data:image/")) return makeImage(`${title} · 图 ${index + 1}`, src, { size: "HTML 图片", sourceHtml: file.name });
      try { const absolute = new URL(src, `file://${file.name}`).href.replace(/^file:\/\//, ""); const proxy = await fetch("/api/proxy-image", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: absolute }) }); const data = await proxy.json(); if (proxy.ok && data.data) return makeImage(`${title} · 图 ${index + 1}`, data.data, { size: "HTML 图片", sourceHtml: file.name }); } catch { /* local relative files may not be reachable */ }
      return null;
    }));
    const usable = imageItems.filter(Boolean);
    if (usable.length) state.images.push(...usable);
    else state.images.push(makeImage(`${title}.html`, demoImage(), { size: "HTML 文件", regions: structuredClone(demoRegions), sourceHtml: file.name, analyzed: false }));
  }
  if (state.images.length) state.currentId = state.images[state.images.length - 1].id;
  render(); showToast(`已读取 ${files.length} 个网页文件`, "success");
}
function fileToDataUrl(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); }); }
function formatBytes(bytes) { if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`; return `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

function applyAnalysisResult(image, result) {
  pushHistory();
  image.regions = (result.regions || []).map((region, index) => ({ ...region, id: region.id || `region-${Date.now()}-${index}`, cropSrc: null, layoutX: null, layoutY: null, layoutW: null, layoutH: null, userMoved: false }));
  image.previewReady = false;
  image.analyzed = true;
  image.supervisionPending = !!result.jobId;
  image.supervisionJobId = result.jobId || null;
  image.supervisionUserEdited = false;
  state.lastAnalyzed = "刚刚";
  state.lastSupervision = result.supervision || null;
  if (state.currentId === image.id) state.selectedRegionId = image.regions[0]?.id || null;
  render();
}

function watchSupervision(image, jobId) {
  if (!jobId) return;
  const poll = async () => {
    if (!image.supervisionPending || image.supervisionJobId !== jobId) return;
    try {
      const response = await fetch(`/api/segment-status?jobId=${encodeURIComponent(jobId)}`);
      if (!response.ok) throw new Error("监督任务暂时不可用");
      const result = await response.json();
      if (result.status !== "complete") return setTimeout(poll, 2500);
      image.supervisionPending = false;
      image.supervisionJobId = null;
      if (image.supervisionUserEdited) {
        image.supervisionResult = result;
        if (state.currentId === image.id) showToast("监督审校已完成；检测到你已手动修改，未覆盖当前编辑", "warn");
        return;
      }
      image.applyingSupervision = true;
      applyAnalysisResult(image, { regions: result.regions || image.regions, supervision: result.supervision || null });
      image.applyingSupervision = false;
      if (state.currentId === image.id) showToast(`后台监督审校完成（${result.supervision?.rounds || 1} 轮）`, result.supervision?.status === "pass" ? "success" : "warn");
    } catch {
      setTimeout(poll, 4000);
    }
  };
  setTimeout(poll, 1200);
}

async function segmentCurrent() {
  const image = currentImage(); if (!image) return showToast("请先选择一张图片", "warn");
  const button = $("#segmentButton"); button.disabled = true; button.innerHTML = '<span class="spinner"></span>正在理解语义…';
  try {
    let result;
    if (image.src.startsWith("data:image/")) { const response = await fetch("/api/segment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: image.src, hint: "优先保持同一题目编号下的图片、图注和结构式完整" }) }); result = await response.json(); if (!response.ok) throw new Error(result.error || "分析失败"); }
    else { result = { regions: structuredClone(demoRegions), source: "offline" }; }
    applyAnalysisResult(image, result);
    if (result.jobId) {
      showToast("首轮分区已返回，监督审校在后台继续", "success");
      watchSupervision(image, result.jobId);
    } else {
      showToast(result.source === "qwen-supervised" ? `Qwen 分割 + 监督审校完成（${result.supervision?.rounds || 1} 轮）` : "已使用离线演示分区（可继续手动调整）", result.source === "qwen-supervised" ? "success" : "warn");
    }
  } catch (error) { showToast(error.message || "分析失败，请稍后重试", "error"); }
  finally { button.disabled = false; button.innerHTML = "<span>✦</span>分析当前图片"; }
}

async function segmentAll() {
  const candidates = state.images.filter((image) => image.src.startsWith("data:image/") && !image.analyzed);
  if (!candidates.length) return showToast("队列中的图片都已分析，可继续人工调整", "warn");
  const batchButton = $("#segmentAllButton"); batchButton.disabled = true; batchButton.innerHTML = '<span class="spinner"></span>批量理解中…';
  let completed = 0;
  try {
    for (const image of candidates) {
      state.currentId = image.id; render();
      try { const response = await fetch("/api/segment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: image.src, hint: "优先保持同一题目编号下的图片、图注和结构式完整" }) }); const result = await response.json(); if (!response.ok) throw new Error(result.error || "分析失败"); applyAnalysisResult(image, result); if (result.jobId) watchSupervision(image, result.jobId); completed++; } catch { image.regions = structuredClone(demoRegions).map((region) => ({ ...region, cropSrc: null, layoutX: null, layoutY: null, layoutW: null, layoutH: null })); image.previewReady = false; image.analyzed = true; completed++; }
    }
    render(); showToast(`已完成 ${completed} 张图片的语义分区`, "success");
  } finally { batchButton.disabled = false; batchButton.textContent = "批量分析素材队列"; }
}

async function importWebpage() {
  const input = $("#urlInput"); const url = input.value.trim(); if (!url) return showToast("请输入网页地址", "warn");
  $("#importUrlButton").disabled = true; $("#urlStatus").textContent = "正在读取网页中的图片资源…";
  try { const response = await fetch("/api/import-url", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }); const result = await response.json(); if (!response.ok) throw new Error(result.error || "网页读取失败"); const urls = result.imageUrls || []; if (!urls.length) { state.images.push(makeImage(`${result.title}.html`, demoImage(), { size: "网页内容", regions: structuredClone(demoRegions), analyzed: false, sourceUrl: result.url })); } else { const imported = await Promise.all(urls.slice(0, 6).map(async (src, index) => { try { const proxy = await fetch("/api/proxy-image", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: src }) }); const data = await proxy.json(); if (proxy.ok && data.data) return makeImage(`${result.title} · 图 ${index + 1}`, data.data, { size: "网页图片", sourceUrl: result.url }); } catch { /* keep remote fallback below */ } return makeImage(`${result.title} · 图 ${index + 1}`, src, { size: "网页图片", remote: true, sourceUrl: result.url }); })); state.images.push(...imported); } state.currentId = state.images[state.images.length - 1].id; render(); $("#urlStatus").textContent = `已导入 ${Math.max(urls.length, 1)} 个网页素材`; showToast("网页素材已加入队列", "success"); }
  catch (error) { $("#urlStatus").textContent = "网页读取失败，请检查地址或网络"; showToast(error.message || "网页读取失败", "error"); }
  finally { $("#importUrlButton").disabled = false; }
}

function resizePaintCanvas() { const canvas = $("#paintLayer"); const frame = $("#outputCanvas"); if (!frame || !frame.clientWidth) return; const ratio = window.devicePixelRatio || 1; canvas.width = Math.round(frame.clientWidth * ratio); canvas.height = Math.round(frame.clientHeight * ratio); canvas.style.width = `${frame.clientWidth}px`; canvas.style.height = `${frame.clientHeight}px`; }
function drawPaint() {
  const canvas = $("#paintLayer"); if (!canvas.width) return; const ctx = canvas.getContext("2d"); const scale = window.devicePixelRatio || 1; ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.save(); ctx.scale(scale, scale);
  state.layoutWhiteRects.forEach((item) => { ctx.fillStyle = "rgba(255,255,255,.98)"; ctx.fillRect(item.x, item.y, item.w, item.h); });
  state.layoutPaintPaths.forEach((path) => { if (path.points.length < 1) return; ctx.strokeStyle = "rgba(255,255,255,.98)"; ctx.lineWidth = path.size; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.beginPath(); path.points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)); ctx.stroke(); });
  ctx.restore();
}

function clearWhiteouts() { const image = currentImage(); if (!image) return; pushHistory(); state.whiteRects[image.id] = []; state.paintPaths[image.id] = []; state.layoutWhiteRects = []; state.layoutPaintPaths = []; renderRegions(); drawPaint(); showToast("已清除当前画布的涂白", "success"); }
function deleteImage(imageId) { const index = state.images.findIndex((image) => image.id === imageId); if (index < 0) return; pushHistory(); state.images.splice(index, 1); delete state.whiteRects[imageId]; delete state.paintPaths[imageId]; if (state.currentId === imageId) { const next = state.images[Math.min(index, state.images.length - 1)]; state.currentId = next?.id || null; state.selectedRegionId = next?.regions[0]?.id || null; } render(); showToast("素材图片已删除", "success"); }
function deleteRegion(imageId, regionId) { const image = state.images.find((item) => item.id === imageId); if (!image) return; const region = image.regions.find((item) => item.id === regionId); if (!region) return; pushHistory(); image.regions = image.regions.filter((item) => item.id !== regionId); if (state.currentId === imageId && state.selectedRegionId === regionId) state.selectedRegionId = image.regions[0]?.id || null; render(); showToast("内容块已移除", "success"); }
function deleteSelected() { const image = currentImage(); if (!image || !state.selectedRegionId) return showToast("请先选择一个内容块", "warn"); deleteRegion(image.id, state.selectedRegionId); }

function saveProject() { const images = state.images.map((image) => ({ ...image, regions: image.regions.map(({ cropSrc, ...region }) => region), syntheticRegion: image.syntheticRegion ? (({ cropSrc, ...region }) => region)(image.syntheticRegion) : undefined })); const data = { version: 2, projectName: state.projectName, images, whiteRects: state.whiteRects, paintPaths: state.paintPaths, layoutWhiteRects: state.layoutWhiteRects, layoutPaintPaths: state.layoutPaintPaths, exportedAt: new Date().toISOString() }; const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${state.projectName || "draft-reformat"}.draft.json`; link.click(); URL.revokeObjectURL(link.href); showToast("项目 JSON 已保存", "success"); }

async function exportFinal() {
  if (!state.images.length) return showToast("请先加入图片素材", "warn");
  const button = $("#exportButton"); button.disabled = true; showToast("正在整理分页，编号集合不会被拆开…", "success");
  try { const html = await buildExportHtml(); const output = window.open("", "_blank"); if (!output) throw new Error("浏览器拦截了预览窗口，请允许弹窗"); output.document.write(html); output.document.close(); } catch (error) { showToast(error.message || "导出失败", "error"); } finally { button.disabled = false; }
}

async function buildExportHtml() {
  const blocks = [];
  for (const image of state.images) {
    const groups = new Map();
    (image.regions.length ? image.regions : [{ id: "full", label: image.name, kind: "other", x: 0, y: 0, w: 100, h: 100, group: "未分组", confidence: 1 }]).forEach((region) => { const key = state.keepGroups ? (region.group || region.id) : region.id; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(region); });
    for (const [group, regions] of groups) { const crops = []; for (const region of regions) crops.push({ region, src: region.cropSrc || await cropRegion(image, region) }); blocks.push({ group, image, regions: crops, y: Math.min(...regions.map((region) => region.layoutY || 0)), height: regions.reduce((sum, region) => sum + (region.layoutH || region.h * 8), 0) + 28 }); }
  }
  blocks.sort((a, b) => a.y - b.y);
  const pages = []; let page = []; let used = 0; const limit = $("#pageSize").value === "a3" ? 1240 : 840;
  blocks.forEach((block) => { const blockHeight = Math.max(90, Math.min(1250, block.height)); if (page.length && used + blockHeight > limit) { pages.push(page); page = []; used = 0; } page.push(block); used += blockHeight; }); if (page.length) pages.push(page);
  const size = $("#pageSize").value; const margin = $("#marginRange").value;
  const pagesHtml = pages.map((items, index) => `<section class="print-page"><div class="page-header"><div><span class="print-kicker">DRAFT REFORMAT · FINAL</span><h1>${escapeHtml(state.projectName)}</h1></div><span class="page-no">${String(index + 1).padStart(2, "0")} / ${String(pages.length).padStart(2, "0")}</span></div>${items.map((block) => `<div class="print-group"><div class="group-title"><span>集合 ${escapeHtml(block.group)}</span><i></i><small>${escapeHtml(block.image.name)}</small></div>${block.regions.map((item) => `<article class="print-block" style="margin-left:${Math.min(110, Math.max(0, item.region.layoutX || 0))}px"><img src="${item.src}" alt="${escapeHtml(item.region.label)}"/><div class="print-caption"><b>${escapeHtml(item.region.label)}</b><span>${kindNames[item.region.kind] || "内容区域"}</span></div></article>`).join("")}</div>`).join("")}<div class="page-footer"><span>语义裁剪 · 人工校订 · 集合不拆页</span><span>${new Date().toLocaleDateString("zh-CN")}</span></div></section>`).join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${escapeHtml(state.projectName)} · 终稿</title><style>@page{size:${size} portrait;margin:0}*{box-sizing:border-box}body{margin:0;background:#e7e8eb;color:#20232b;font-family:Inter,Arial,"Microsoft YaHei",sans-serif}.print-page{width:${size === "a3" ? "1123px" : "794px"};min-height:${size === "a3" ? "1587px" : "1123px"};padding:${margin}px;page-break-after:always;background:#fff;margin:24px auto;display:flex;flex-direction:column}.page-header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid #d9dce2;padding-bottom:15px;margin-bottom:20px}.print-kicker{font-size:8px;letter-spacing:.2em;color:#765fce;font-weight:bold}.page-header h1{margin:7px 0 0;font-size:22px;letter-spacing:-.02em}.page-no{font-size:10px;color:#8a919d;border:1px solid #dfe2e8;padding:5px 7px;border-radius:4px}.print-group{border:1px solid #e2e4e8;border-radius:7px;padding:12px;margin-bottom:14px;break-inside:avoid}.group-title{font-size:10px;color:#6e5bb7;display:flex;align-items:center;gap:8px;margin-bottom:10px}.group-title i{height:1px;background:#ebeaf1;flex:1}.group-title small{font-size:8px;color:#9aa0aa;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.print-block{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end;margin-top:8px;break-inside:avoid}.print-block img{max-width:100%;width:100%;max-height:490px;object-fit:contain;object-position:left top;border:1px solid #eff0f2;border-radius:3px;background:#fcfcfc}.print-caption{font-size:9px;color:#606873;white-space:nowrap;writing-mode:vertical-rl;max-height:130px}.print-caption b{color:#303641;font-size:10px;margin-bottom:5px}.page-footer{margin-top:auto;padding-top:16px;border-top:1px solid #e6e7e9;display:flex;justify-content:space-between;color:#a0a6af;font-size:8px}@media print{body{background:#fff}.print-page{margin:0;box-shadow:none}}@media screen{.print-page{box-shadow:0 10px 35px rgba(30,33,40,.13)}}.print-help{position:fixed;right:20px;top:20px;background:#27243d;color:#eee;padding:10px 13px;border-radius:6px;font-size:11px}@media print{.print-help{display:none}}</style></head><body><div class="print-help">已生成 ${pages.length} 页 · 使用 Ctrl/Cmd + P 保存为 PDF</div>${pagesHtml}<script>setTimeout(()=>window.print(),600)<\/script></body></html>`;
}

function cropRegion(image, region) { return new Promise((resolve) => { const img = new Image(); img.onload = () => { try { const sx = img.naturalWidth * region.x / 100; const sy = img.naturalHeight * region.y / 100; const sw = img.naturalWidth * region.w / 100; const sh = img.naturalHeight * region.h / 100; const canvas = document.createElement("canvas"); const scale = Math.min(1, 1200 / Math.max(sw, sh)); canvas.width = Math.max(1, Math.round(sw * scale)); canvas.height = Math.max(1, Math.round(sh * scale)); const ctx = canvas.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height); drawCropWhiteouts(ctx, image, region, canvas.width, canvas.height); resolve(canvas.toDataURL("image/jpeg", .92)); } catch { resolve(image.src); } }; img.onerror = () => resolve(image.src); img.src = image.src; }); }
function drawCropWhiteouts(ctx, image, region, width, height) {
  (state.whiteRects[image.id] || []).forEach((item) => { const x = (item.x - region.x) / region.w * width; const y = (item.y - region.y) / region.h * height; const w = item.w / region.w * width; const h = item.h / region.h * height; ctx.fillStyle = "#fff"; ctx.fillRect(x, y, w, h); });
  (state.paintPaths[image.id] || []).forEach((path) => { if (path.points.length < 1) return; ctx.strokeStyle = "#fff"; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.lineWidth = path.size / region.w * width; ctx.beginPath(); path.points.forEach((point, index) => { const x = (point.x - region.x) / region.w * width; const y = (point.y - region.y) / region.h * height; index ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); });
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character])); }
function showToast(message, type = "success") { const toast = document.createElement("div"); toast.className = `toast ${type}`; toast.textContent = message; $("#toastStack").appendChild(toast); setTimeout(() => toast.remove(), 3400); }

init();
