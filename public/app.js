/* Draft ReFormat — browser-side editor. */
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const kindNames = {
  text: "文字段落", image: "图片 / 插图", table: "表格", chemistry: "化学结构式",
  biology: "生物图片", formula: "数学公式", diagram: "图示 / 示意图",
  chemical: "化学结构式", annotation: "批注 / 修正", other: "其他内容"
};
const kindShort = { text: "TEXT", image: "IMAGE", table: "TABLE", chemistry: "CHEM", biology: "BIO", formula: "FORMULA", diagram: "DIAGRAM", chemical: "CHEM", annotation: "NOTE", other: "BLOCK" };
const kindColors = { text: "#ac8cff", image: "#61d7d4", table: "#63d7aa", chemistry: "#eec77a", biology: "#61d7d4", formula: "#eec77a", diagram: "#61d7d4", chemical: "#eec77a", annotation: "#ac8cff", other: "#9aa3b4" };
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
  selectedRegionKeys: [],
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
  showModelBoundaries: true,
  keepGroups: true,
  draggingImageId: null,
  suppressTileClick: false,
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
  state.selectedRegionKeys = [regionKey(demo.id, demoRegions[1].id)];
  bindEvents();
  render();
  showToast("已加载演示草稿，可直接拖动分区开始编辑", "success");
}

function currentImage() { return state.images.find((image) => image.id === state.currentId) || null; }
function selectedRegion() { const image = currentImage(); return image?.regions.find((region) => region.id === state.selectedRegionId) || null; }
function regionKey(imageId, regionId) { return `${imageId}::${regionId}`; }
function selectedRegionEntries() {
  const entries = [];
  for (const key of state.selectedRegionKeys || []) {
    const split = key.indexOf("::");
    const imageId = key.slice(0, split), regionId = key.slice(split + 2);
    const image = state.images.find((item) => item.id === imageId);
    const region = image?.regions.find((item) => item.id === regionId);
    if (image && region) entries.push({ image, region });
  }
  if (!entries.length) { const image = currentImage(), region = selectedRegion(); if (image && region) entries.push({ image, region }); }
  return entries;
}
function setSelection(entries, primary = entries[0]) {
  state.selectedRegionKeys = [...new Set(entries.map(({ image, region }) => regionKey(image.id, region.id)))];
  if (primary) { state.currentId = primary.image.id; state.selectedRegionId = primary.region.id; }
  else { state.selectedRegionId = null; }
  updateTileSelectionClasses();
}
function updateTileSelectionClasses() {
  const keys = new Set(state.selectedRegionKeys || []);
  $$(".region-tile").forEach((tile) => {
    const selected = keys.has(regionKey(tile.dataset.imageId, tile.dataset.regionId));
    tile.classList.toggle("selected", selected && tile.dataset.imageId === state.currentId && tile.dataset.regionId === state.selectedRegionId);
    tile.classList.toggle("multi-selected", selected && (state.selectedRegionKeys || []).length > 1);
  });
}
function snapshot() { return JSON.stringify({ images: state.images, currentId: state.currentId, selectedRegionId: state.selectedRegionId, selectedRegionKeys: state.selectedRegionKeys, paintPaths: state.paintPaths, whiteRects: state.whiteRects, layoutWhiteRects: state.layoutWhiteRects, layoutPaintPaths: state.layoutPaintPaths }); }
function restoreSnapshot(value) { const parsed = JSON.parse(value); state.images = parsed.images; state.currentId = parsed.currentId; state.selectedRegionId = parsed.selectedRegionId; state.selectedRegionKeys = parsed.selectedRegionKeys || []; state.paintPaths = parsed.paintPaths || {}; state.whiteRects = parsed.whiteRects || {}; state.layoutWhiteRects = parsed.layoutWhiteRects || []; state.layoutPaintPaths = parsed.layoutPaintPaths || []; render(); }
function pushHistory() {
  const image = currentImage();
  if (image?.supervisionPending && !image.applyingSupervision) image.supervisionUserEdited = true;
  state.history.push(snapshot()); if (state.history.length > 35) state.history.shift(); state.redo = [];
}
function pushHistorySnapshot(before) {
  if (!before || before === snapshot()) return;
  const image = currentImage();
  if (image?.supervisionPending && !image.applyingSupervision) image.supervisionUserEdited = true;
  state.history.push(before); if (state.history.length > 35) state.history.shift(); state.redo = [];
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
  list.innerHTML = state.images.map((image, index) => `<div class="asset-item ${image.id === state.currentId ? "active" : ""}" data-image-id="${image.id}" draggable="true" title="拖动排序素材页面">
    <img class="asset-thumb" src="${image.src}" alt=""/><div class="asset-info"><div class="asset-name">${escapeHtml(image.name)}</div><div class="asset-meta"><i></i>${image.regions.length ? `${image.regions.length} 个内容块` : "待分析"}<span>·</span>${image.size || "网页素材"}</div></div><span class="asset-index">${String(index + 1).padStart(2, "0")}</span><span class="asset-move-actions"><button data-move-image="${image.id}" data-direction="-1" aria-label="上移 ${escapeHtml(image.name)}" title="上移素材" ${index === 0 ? "disabled" : ""}>↑</button><button data-move-image="${image.id}" data-direction="1" aria-label="下移 ${escapeHtml(image.name)}" title="下移素材" ${index === state.images.length - 1 ? "disabled" : ""}>↓</button></span><button class="asset-delete" data-delete-image="${image.id}" title="删除素材">×</button></div>`).join("");
  $$(".asset-item").forEach((item) => {
    item.addEventListener("click", () => { if (state.draggingImageId) return; const image = state.images.find((entry) => entry.id === item.dataset.imageId); if (!image) return; state.currentId = image.id; setSelection(image.regions[0] ? [{ image, region: image.regions[0] }] : []); render(); });
    item.addEventListener("dragstart", (event) => { state.draggingImageId = item.dataset.imageId; item.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", state.draggingImageId); });
    item.addEventListener("dragover", (event) => { if (!state.draggingImageId || state.draggingImageId === item.dataset.imageId) return; event.preventDefault(); item.classList.add("drop-target"); });
    item.addEventListener("dragleave", () => item.classList.remove("drop-target"));
    item.addEventListener("drop", (event) => { event.preventDefault(); item.classList.remove("drop-target"); const sourceId = state.draggingImageId || event.dataTransfer.getData("text/plain"); reorderAssets(sourceId, item.dataset.imageId); });
    item.addEventListener("dragend", () => { state.draggingImageId = null; $$(".asset-item").forEach((entry) => entry.classList.remove("dragging", "drop-target")); });
  });
  $$("[data-delete-image]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); deleteImage(button.dataset.deleteImage); }));
  $$("[data-move-image]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); moveAsset(button.dataset.moveImage, Number(button.dataset.direction)); }));
}

function renderRegions() {
  const layer = $("#regionLayer");
  const items = visualRegions();
  const positionedItems = items.filter(({ region }) => hasRegionLayout(region));
  layer.innerHTML = `${positionedItems.map(({ image, region }) => `<div class="region-tile ${region.id === state.selectedRegionId && image.id === state.currentId ? "selected" : ""} ${(state.selectedRegionKeys || []).includes(regionKey(image.id, region.id)) && (state.selectedRegionKeys || []).length > 1 ? "multi-selected" : ""} ${region.cropSrc ? "" : "crop-preview-pending"}" data-region-id="${region.id}" data-image-id="${image.id}" data-kind="${region.kind}" data-tool="${state.tool}" style="left:${region.layoutX}px;top:${region.layoutY}px;width:${region.layoutW}px;height:${region.layoutH}px;border-color:${kindColors[region.kind] || kindColors.other};z-index:${region.zIndex || 2}">
    ${region.cropSrc ? `<img src="${region.cropSrc}" alt="${escapeHtml(region.label)}" draggable="false"/>` : ""}${renderRegionBoundarySvg(region, 100, 100, "model-boundary-overlay", region.layoutW, region.layoutH)}<div class="tile-label"><span>${escapeHtml(region.label)}</span><i>${escapeHtml(region.group || "—")}</i></div><span class="tile-kind">${kindShort[region.kind] || "BLOCK"}</span></div>`).join("")}`;
  $$(".region-tile").forEach((box) => {
    box.addEventListener("pointerdown", (event) => startRegionPointer(event, box));
    box.addEventListener("click", (event) => {
      event.stopPropagation();
      if (state.suppressTileClick) { state.suppressTileClick = false; return; }
      const image = state.images.find((item) => item.id === box.dataset.imageId), region = image?.regions.find((item) => item.id === box.dataset.regionId);
      if (!image || !region) return;
      const entry = { image, region };
      if (event.shiftKey) {
        const entries = selectedRegionEntries(), key = regionKey(image.id, region.id);
        setSelection(entries.some((item) => regionKey(item.image.id, item.region.id) === key) ? entries.filter((item) => regionKey(item.image.id, item.region.id) !== key) : [...entries, entry], entry);
      } else setSelection([entry], entry);
      renderRegions(); renderInspector();
    });
  });
  updateOutputCanvasSize(positionedItems);
  updateBoundaryVisibility();
  if (!state.hydrating && items.some(({ region, image }) => !region.cropSrc && (!region.synthetic || !image.previewReady))) hydrateVisualRegions();
}

function hasRegionLayout(region) {
  return Number.isFinite(region.layoutX) && Number.isFinite(region.layoutY)
    && Number.isFinite(region.layoutW) && region.layoutW > 0
    && Number.isFinite(region.layoutH) && region.layoutH > 0;
}

function renderRegionBoundarySvg(region, targetWidth, targetHeight, className, visualWidth = targetWidth, visualHeight = targetHeight) {
  if (!region || region.synthetic) return "";
  const polygon = regionPolygon(region);
  const sourceX = Number(region.x) || 0, sourceY = Number(region.y) || 0;
  const sourceW = Math.max(.001, Number(region.w) || 1), sourceH = Math.max(.001, Number(region.h) || 1);
  const map = ([x, y]) => [((Number(x) - sourceX) / sourceW * targetWidth).toFixed(3), ((Number(y) - sourceY) / sourceH * targetHeight).toFixed(3)];
  const polygons = [polygon, ...(region.holes || []).map((hole) => hole?.polygon).filter((points) => Array.isArray(points) && points.length >= 3)];
  const compensateX = targetWidth / Math.max(.001, Number(visualWidth) || targetWidth);
  const compensateY = targetHeight / Math.max(.001, Number(visualHeight) || targetHeight);
  const geometry = polygons.map((points) => {
    const mapped = points.map(map).map(([x, y]) => [Number(x), Number(y)]);
    const coords = mapped.map((point) => point.map((value) => value.toFixed(3)).join(",")).join(" ");
    const center = [mapped.reduce((sum, point) => sum + point[0], 0) / mapped.length, mapped.reduce((sum, point) => sum + point[1], 0) / mapped.length];
    const vertices = mapped.map(([x, y], index) => {
      const placeLeft = x > center[0], placeBelow = y < center[1];
      const labelX = placeLeft ? -5 : 5;
      const labelY = placeBelow ? Math.min((Number(visualHeight) || targetHeight) * .42, 28) : -Math.min((Number(visualHeight) || targetHeight) * .42, 8);
      return `<g class="boundary-vertex" transform="translate(${x.toFixed(3)} ${y.toFixed(3)})"><g transform="scale(${compensateX} ${compensateY})"><circle r="3"></circle><text x="${labelX}" y="${labelY}" text-anchor="${placeLeft ? "end" : "start"}">V${index + 1}</text></g></g>`;
    }).join("");
    return `<polygon class="model-boundary-underlay" points="${coords}"/><polygon class="model-boundary-line" points="${coords}"/>${vertices}`;
  }).join("");
  return `<svg class="${className}" viewBox="0 0 ${targetWidth} ${targetHeight}" preserveAspectRatio="none" aria-hidden="true">${geometry}</svg>`;
}

function updateBoundaryVisibility() {
  const hidden = !state.showModelBoundaries;
  $("#outputCanvas")?.classList.toggle("model-boundaries-hidden", hidden);
  $("#selectedPreview")?.classList.toggle("model-boundaries-hidden", hidden);
  const button = $("#boundaryLabelsToggle");
  if (button) {
    button.classList.toggle("active", !hidden);
    button.setAttribute("aria-pressed", String(!hidden));
    button.title = hidden ? "显示模型多边形边界与顶点编号" : "隐藏模型多边形边界与顶点编号";
  }
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
  const bottom = items.reduce((max, item) => Math.max(max, item.region.layoutY + item.region.layoutH), 0);
  canvas.style.height = `${Math.max(1120, bottom + 44)}px`;
  canvas.style.minHeight = `${Math.max(1120, bottom + 44)}px`;
}

async function hydrateVisualRegions() {
  if (state.hydrating) return;
  state.hydrating = true;
  try {
    const items = visualRegions();
    const images = [...new Set(items.map(({ image }) => image))];
    await Promise.all(images.map(ensureImageMetrics));

    // Establish every block's real size and vertical position before any crop
    // decoding starts. Otherwise newly analyzed blocks briefly render as 1px
    // tiles at (28,28), which looks like the whole result collapsed to the corner.
    normalizeLongLayout();
    renderRegions();

    for (const { image, region } of items) {
      if (region.synthetic) { region.layoutW = 740; region.layoutH = Math.round(740 / (image.aspect || .72)); }
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

async function ensureImageMetrics(image) {
  if (image.sourceWidth && image.sourceHeight && image.aspect) return;
  const size = await imageSize(image.src);
  image.sourceWidth = size.width;
  image.sourceHeight = size.height;
  image.aspect = size.width && size.height ? size.width / size.height : .72;
  // Fit large source images to the canvas, but never upscale a small one.
  image.displayScale = Math.min(1, 760 / Math.max(1, image.sourceWidth));
}

function imageSize(src) { return new Promise((resolve) => { const img = new Image(); img.onload = () => resolve({ width: img.naturalWidth || 760, height: img.naturalHeight || Math.round(760 / .72) }); img.onerror = () => resolve({ width: 760, height: Math.round(760 / .72) }); img.src = src; }); }

function initializeRegionLayout(region, image) {
  const baseWidth = Math.min(760, image.sourceWidth || 760);
  const scale = image.displayScale || (baseWidth / Math.max(1, image.sourceWidth || baseWidth));
  // Keep the crop's native proportions and never enlarge a source image.
  const sourceW = Math.max(0.1, Number(region.w) || 100);
  const sourceH = Math.max(0.1, Number(region.h) || 100);
  region.layoutW = Math.max(1, Math.round((image.sourceWidth || baseWidth) * sourceW / 100 * scale));
  region.layoutH = Math.max(1, Math.round((image.sourceHeight || baseWidth / (image.aspect || .72)) * sourceH / 100 * scale));
  region.layoutX = 28;
  const all = visualRegions().filter(({ region: item }) => item !== region && item.layoutY != null);
  const last = all.reduce((max, item) => Math.max(max, item.region.layoutY + item.region.layoutH), 30);
  region.layoutY = last + 24;
}

function normalizeLongLayout() {
  let y = 28;
  state.images.forEach((image) => {
    const regions = image.regions.length ? image.regions : (image.syntheticRegion ? [image.syntheticRegion] : []);
    regions.forEach((region) => {
      if (!hasRegionLayout(region)) initializeRegionLayout(region, image);
      if (!region.userMoved) { region.layoutX = 28; region.layoutY = y; }
      if (!Number.isFinite(region.layoutX)) region.layoutX = 28;
      if (!Number.isFinite(region.layoutY)) region.layoutY = y;
      y = Math.max(y, region.layoutY + region.layoutH + 24);
    });
    y += 20;
  });
  captureHomePageLayout();
}

function captureHomePageLayout() {
  state.images.forEach((image) => {
    const regions = image.regions.length ? image.regions : (image.syntheticRegion ? [image.syntheticRegion] : []);
    if (!regions.length || regions.some((region) => !hasRegionLayout(region))) return;
    const top = Math.min(...regions.map((region) => Number.isFinite(region.layoutY) ? region.layoutY : 28));
    const bottom = Math.max(...regions.map((region) => (Number.isFinite(region.layoutY) ? region.layoutY : top) + (Number.isFinite(region.layoutH) ? region.layoutH : 1)));
    if (!Number.isFinite(image.homePageHeight)) image.homePageHeight = bottom - top;
    regions.forEach((region) => {
      if (!Number.isFinite(region.homeLayoutX)) region.homeLayoutX = Number.isFinite(region.layoutX) ? region.layoutX : 28;
      if (!Number.isFinite(region.homeLayoutY)) region.homeLayoutY = (Number.isFinite(region.layoutY) ? region.layoutY : top) - top;
    });
  });
}

function restoreHomePagePositions() {
  captureHomePageLayout();
  let pageTop = 28;
  state.images.forEach((image) => {
    const regions = image.regions.length ? image.regions : (image.syntheticRegion ? [image.syntheticRegion] : []);
    image.layoutPageY = pageTop;
    let pageBottom = 0;
    regions.forEach((region) => {
      region.layoutX = Number.isFinite(region.homeLayoutX) ? region.homeLayoutX : 28;
      region.layoutY = pageTop + (Number.isFinite(region.homeLayoutY) ? region.homeLayoutY : 0);
      region.userMoved = false;
      pageBottom = Math.max(pageBottom, (region.homeLayoutY || 0) + (region.layoutH || 1));
    });
    const pageHeight = Math.max(Number(image.homePageHeight) || 0, pageBottom);
    image.homePageHeight = pageHeight;
    pageTop += pageHeight + 40;
  });
}

function reorderAssets(sourceId, targetId, sortedImages = null) {
  if (sortedImages) {
    if (state.images.every((image, index) => image.id === sortedImages[index]?.id)) return;
    pushHistory(); captureHomePageLayout(); state.images = sortedImages; restoreHomePagePositions();
  } else {
    if (!sourceId || !targetId || sourceId === targetId) { state.draggingImageId = null; return; }
    const from = state.images.findIndex((image) => image.id === sourceId), to = state.images.findIndex((image) => image.id === targetId);
    if (from < 0 || to < 0) return;
    pushHistory(); captureHomePageLayout();
    const [image] = state.images.splice(from, 1); state.images.splice(to, 0, image); restoreHomePagePositions();
  }
  state.draggingImageId = null;
  render();
  showToast("素材页面已重排；各块随来源页移动，跨页块已归回原页", "success");
}

function moveAsset(imageId, offset) {
  const from = state.images.findIndex((image) => image.id === imageId);
  const to = clamp(from + offset, 0, state.images.length - 1);
  if (from < 0 || from === to) return;
  const sorted = [...state.images], [image] = sorted.splice(from, 1);
  sorted.splice(to, 0, image);
  reorderAssets(null, null, sorted);
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
  const entries = selectedRegionEntries();
  const region = selectedRegion();
  const multi = entries.length > 1;
  $("#multiSelectionSummary").hidden = !multi;
  $("#multiSelectionCount").textContent = `${entries.length} 个内容块已选中`;
  $("#noSelection").hidden = entries.length > 0;
  $("#regionInspector").hidden = entries.length === 0;
  $("#regionInspector").classList.toggle("multi-mode", multi);
  $("#removeInspectorRegion").textContent = multi ? `移除选中的 ${entries.length} 个内容块` : "移除该内容块";
  if (!region) return;
  $("#previewType").textContent = kindShort[region.kind] || "BLOCK";
  $("#previewGroup").textContent = `集合 ${region.group || "—"}`;
  $("#regionLabel").value = region.label;
  $("#regionKind").textContent = kindNames[region.kind] || kindNames.other;
  $("#regionGroup").value = region.group || "";
  $("#groupBadge").textContent = region.group || "—";
  renderPolygonEditor(region);
  $$("#regionInspector .single-region-control :is(input,button,select)").forEach((control) => { control.disabled = multi; });
  const confidence = Math.round((region.confidence ?? .6) * 100); $("#confidenceValue").textContent = `${confidence}%`; $("#confidenceBar").style.width = `${confidence}%`; $("#regionDescription").textContent = region.description || "语义内容区域";
}

function regionPolygon(region) {
  if (Array.isArray(region.polygon) && region.polygon.length >= 3) return region.polygon;
  const x = Number(region.x) || 0, y = Number(region.y) || 0;
  const w = Number(region.w) || 1, h = Number(region.h) || 1;
  region.polygon = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
  return region.polygon;
}

function renderPolygonEditor(region) {
  const polygon = regionPolygon(region);
  const xs = polygon.map((point) => Number(point[0])), ys = polygon.map((point) => Number(point[1]));
  const minX = Math.min(...xs), minY = Math.min(...ys), width = Math.max(.001, Math.max(...xs) - minX), height = Math.max(.001, Math.max(...ys) - minY);
  $("#polygonPreview").setAttribute("viewBox", `0 0 ${width} ${height}`);
  const previewRect = $("#polygonPreview").getBoundingClientRect();
  $("#polygonPreview").innerHTML = `<polygon class="preview-polygon-fill" points="${polygon.map(([x, y]) => `${(x - minX).toFixed(3)},${(y - minY).toFixed(3)}`).join(" ")}"/>${renderRegionBoundarySvg(region, width, height, "preview-model-boundary", previewRect.width, previewRect.height)}`;
  $("#polygonVertices").innerHTML = polygon.map(([x, y], index) => `<div class="polygon-vertex-row" data-vertex-index="${index}"><strong>V${index + 1}</strong><label>X<input type="number" min="0" max="100" step="0.1" value="${Number(x).toFixed(2)}" data-vertex-axis="0" aria-label="顶点 ${index + 1} X" /></label><label>Y<input type="number" min="0" max="100" step="0.1" value="${Number(y).toFixed(2)}" data-vertex-axis="1" aria-label="顶点 ${index + 1} Y" /></label><button type="button" data-remove-vertex="${index}" title="移除此顶点" ${polygon.length <= 3 ? "disabled" : ""}>×</button></div>`).join("");
  updateBoundaryVisibility();
}

function polygonArea(polygon) {
  return Math.abs(polygon.reduce((sum, [x, y], index) => {
    const [nextX, nextY] = polygon[(index + 1) % polygon.length];
    return sum + x * nextY - nextX * y;
  }, 0)) / 2;
}

function polygonSelfIntersects(polygon) {
  const orient = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const intersects = (a, b, c, d) => {
    const abC = orient(a, b, c), abD = orient(a, b, d), cdA = orient(c, d, a), cdB = orient(c, d, b);
    return abC * abD < -1e-9 && cdA * cdB < -1e-9;
  };
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i], b = polygon[(i + 1) % polygon.length];
    for (let j = i + 1; j < polygon.length; j++) {
      if (j === i || j === (i + 1) % polygon.length || i === (j + 1) % polygon.length) continue;
      if (intersects(a, b, polygon[j], polygon[(j + 1) % polygon.length])) return true;
    }
  }
  return false;
}

function setRegionPolygon(image, region, polygon) {
  if (!Array.isArray(polygon) || polygon.length < 3 || polygon.some((point) => !Array.isArray(point) || point.length !== 2 || point.some((value) => typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100)) || polygonArea(polygon) < .001 || polygonSelfIntersects(polygon)) {
    showToast("多边形无效：请检查顶点范围、面积及交叉边", "warn");
    return false;
  }
  const oldX = Number(region.x) || 0, oldY = Number(region.y) || 0;
  const oldW = Math.max(.001, Number(region.w) || 1), oldH = Math.max(.001, Number(region.h) || 1);
  const xs = polygon.map(([x]) => x), ys = polygon.map(([, y]) => y);
  const x = Math.min(...xs), y = Math.min(...ys), w = Math.max(...xs) - x, h = Math.max(...ys) - y;
  const sourceWidth = Number(image.sourceWidth) || 760, sourceHeight = Number(image.sourceHeight) || 1000;
  const scale = Number(image.displayScale) || Math.min(1, 760 / Math.max(1, sourceWidth));
  const dx = (x - oldX) / 100 * sourceWidth * scale, dy = (y - oldY) / 100 * sourceHeight * scale;
  if (hasRegionLayout(region)) {
    region.layoutX += dx; region.layoutY += dy;
    region.layoutW = Math.max(1, sourceWidth * w / 100 * scale);
    region.layoutH = Math.max(1, sourceHeight * h / 100 * scale);
  }
  if (Number.isFinite(region.homeLayoutX)) region.homeLayoutX += dx;
  if (Number.isFinite(region.homeLayoutY)) region.homeLayoutY += dy;
  const remapLocalPoint = ([px, py]) => [((oldX + Number(px) * oldW / 100) - x) / w * 100, ((oldY + Number(py) * oldH / 100) - y) / h * 100];
  if (Array.isArray(region.whiteoutPolygons)) region.whiteoutPolygons = region.whiteoutPolygons.map((points) => points.map(remapLocalPoint));
  if (Array.isArray(region.whiteoutPaths)) region.whiteoutPaths = region.whiteoutPaths.map((path) => ({
    ...path,
    points: (path.points || []).map(remapLocalPoint),
    width: (Number(path.width) || 1) * oldW / w,
  }));
  region.x = x; region.y = y; region.w = w; region.h = h; region.polygon = polygon.map(([px, py]) => [+px.toFixed(3), +py.toFixed(3)]);
  region.userMoved = true;
  region.cropSrc = null;
  image.previewReady = false;
  return true;
}

function editPolygonVertex(index, axis, value) {
  const { image, region } = selectedRegionEntries()[0] || {};
  if (!image || !region || !Number.isFinite(value)) return;
  const polygon = regionPolygon(region).map((point) => [...point]);
  if (!polygon[index] || ![0, 1].includes(axis)) return;
  polygon[index][axis] = clamp(value, 0, 100);
  pushHistory();
  if (setRegionPolygon(image, region, polygon)) render();
  else renderInspector();
}

function addPolygonVertex() {
  const { image, region } = selectedRegionEntries()[0] || {};
  if (!image || !region) return;
  const polygon = regionPolygon(region).map((point) => [...point]);
  const sourceWidth = Number(image.sourceWidth) || 760, sourceHeight = Number(image.sourceHeight) || 1000;
  let edgeIndex = 0, longest = -1;
  polygon.forEach((point, index) => {
    const next = polygon[(index + 1) % polygon.length];
    const length = ((next[0] - point[0]) * sourceWidth) ** 2 + ((next[1] - point[1]) * sourceHeight) ** 2;
    if (length > longest) { longest = length; edgeIndex = index; }
  });
  const next = polygon[(edgeIndex + 1) % polygon.length];
  polygon.splice(edgeIndex + 1, 0, [(polygon[edgeIndex][0] + next[0]) / 2, (polygon[edgeIndex][1] + next[1]) / 2]);
  pushHistory();
  if (setRegionPolygon(image, region, polygon)) render();
}

function removePolygonVertex(index) {
  const { image, region } = selectedRegionEntries()[0] || {};
  if (!image || !region) return;
  const polygon = regionPolygon(region).map((point) => [...point]);
  if (polygon.length <= 3 || index < 0 || index >= polygon.length) return;
  polygon.splice(index, 1); pushHistory();
  if (setRegionPolygon(image, region, polygon)) render();
  else renderInspector();
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
  $("#splitRegionButton").addEventListener("click", segmentSelectedRegion);
  $("#reanalyzeRegionButton").addEventListener("click", reanalyzeSelectedRegion);
  $("#boundaryLabelsToggle").addEventListener("click", () => { state.showModelBoundaries = !state.showModelBoundaries; updateBoundaryVisibility(); });
  $("#clearWhiteouts").addEventListener("click", clearWhiteouts);
  $("#renameProject").addEventListener("click", () => { const name = prompt("项目名称", state.projectName); if (name?.trim()) { state.projectName = name.trim(); render(); } });
  $("#sortImages").addEventListener("click", () => reorderAssets(null, null, [...state.images].sort((a, b) => a.name.localeCompare(b.name, "zh", { numeric: true }))));
  $("#sortImagesByName").addEventListener("click", () => reorderAssets(null, null, [...state.images].sort((a, b) => a.name.localeCompare(b.name, "zh"))));
  $("#kindSelect").addEventListener("click", () => $("#kindMenu").classList.toggle("open"));
  $$("#kindMenu button").forEach((button) => button.addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.kind = button.dataset.kind; render(); }));
  $$(".suggestion-row button").forEach((button) => button.addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.label = button.dataset.label; render(); }));
  $("#regionLabel").addEventListener("change", (event) => updateSelected("label", event.target.value));
  $("#regionGroup").addEventListener("change", (event) => updateSelected("group", event.target.value || "A"));
  $("#newGroupButton").addEventListener("click", () => { const region = selectedRegion(); if (!region) return; pushHistory(); region.group = nextGroup(); render(); });
  $("#polygonVertices").addEventListener("change", (event) => { const input = event.target.closest("[data-vertex-axis]"); if (!input) return; editPolygonVertex(Number(input.closest("[data-vertex-index]").dataset.vertexIndex), Number(input.dataset.vertexAxis), input.value.trim() === "" ? NaN : Number(input.value)); });
  $("#polygonVertices").addEventListener("click", (event) => { const button = event.target.closest("[data-remove-vertex]"); if (button) removePolygonVertex(Number(button.dataset.removeVertex)); });
  $("#addPolygonVertex").addEventListener("click", addPolygonVertex);
  $("#layerBottom").addEventListener("click", () => changeLayer("bottom")); $("#layerDown").addEventListener("click", () => changeLayer("down")); $("#layerUp").addEventListener("click", () => changeLayer("up")); $("#layerTop").addEventListener("click", () => changeLayer("top"));
  $("#keepGroupsToggle").addEventListener("click", () => { state.keepGroups = !state.keepGroups; $("#keepGroupsToggle").classList.toggle("on", state.keepGroups); });
  $("#pageMargin").addEventListener("change", (event) => { event.target.value = String(clamp(Number(event.target.value), 0, 120)); });
  $$(".tool-button").forEach((button) => button.addEventListener("click", () => setTool(button.dataset.tool)));
  const frame = $("#canvasFrame");
  frame.addEventListener("pointerdown", startCanvasPointer);
  document.addEventListener("keydown", (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); } if (event.key === "Escape") { setTool("select"); $("#kindMenu").classList.remove("open"); } });
  window.addEventListener("resize", () => { resizePaintCanvas(); drawPaint(); });
  $("#canvasArea").addEventListener("wheel", (event) => { if (Math.abs(event.deltaY) > 0) { event.preventDefault(); $("#canvasArea").scrollTop += event.deltaY; } }, { passive: false });
}

function setTool(tool) { state.tool = tool; setToolVisuals(); $$(".region-tile").forEach((tile) => { tile.dataset.tool = tool; }); }
function setToolVisuals() { $$(".tool-button").forEach((button) => button.classList.toggle("active", button.dataset.tool === state.tool)); const name = { select: "选择", draw: "分区", brush: "涂白", cover: "覆盖" }[state.tool]; $("#toolHint").textContent = name; }
function applyZoom() { $("#zoomLabel").textContent = `${Math.round(state.zoom * 100)}%`; const canvas = $("#outputCanvas"); if (canvas) canvas.style.zoom = state.zoom; $("#canvasWrap").style.width = "820px"; }

function startRegionPointer(event, box) {
  event.stopPropagation(); event.preventDefault();
  const image = state.images.find((item) => item.id === box.dataset.imageId);
  const region = image?.regions.find((item) => item.id === box.dataset.regionId);
  if (!image || !region) return;
  const entry = { image, region }, key = regionKey(image.id, region.id);
  if (state.tool === "draw") return startPolygonCut(event, box, entry);
  if (state.tool === "cover") return startRegionCover(event, box, entry);
  if (state.tool === "brush") return startRegionBrush(event, box, entry);

  if (event.shiftKey) {
    const entries = selectedRegionEntries();
    setSelection(entries.some((item) => regionKey(item.image.id, item.region.id) === key)
      ? entries.filter((item) => regionKey(item.image.id, item.region.id) !== key)
      : [...entries, entry], entry);
    renderInspector(); renderRegions(); state.suppressTileClick = true;
    return;
  }
  const currentEntries = selectedRegionEntries();
  const selected = currentEntries.some((item) => regionKey(item.image.id, item.region.id) === key)
    ? currentEntries : [entry];
  setSelection(selected, entry);
  renderInspector(); updateTileSelectionClasses();
  const before = snapshot(), sx = event.clientX, sy = event.clientY, scale = state.zoom || 1;
  const origins = selectedRegionEntries().map((item) => ({ ...item, x: item.region.layoutX, y: item.region.layoutY }));
  let moved = false;
  const move = (moveEvent) => {
    const dx = (moveEvent.clientX - sx) / scale, dy = (moveEvent.clientY - sy) / scale;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 2) return;
    moved = true;
    origins.forEach(({ region: item, x, y }) => {
      item.layoutX = clamp(x + dx, 8, Math.max(8, 800 - (item.layoutW || 1)));
      item.layoutY = Math.max(8, y + dy); item.userMoved = true;
    });
    renderRegions();
  };
  const up = () => {
    if (moved) { pushHistorySnapshot(before); state.suppressTileClick = true; renderInspector(); }
    window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function startCanvasPointer(event) {
  if (event.target.closest(".region-box, .region-tile") || !currentImage()) return;
  if (state.tool !== "select") { showToast("请在现有内容块上操作：分区会抠出多边形，涂白/覆盖只作用于该块", "warn"); return; }
  event.preventDefault();
  const canvasRect = $("#outputCanvas").getBoundingClientRect(), start = canvasPoint(event.clientX, event.clientY, canvasRect);
  const marquee = document.createElement("div"); marquee.className = "selection-marquee"; $("#regionLayer").appendChild(marquee);
  const move = (moveEvent) => {
    const now = canvasPoint(moveEvent.clientX, moveEvent.clientY, canvasRect), rect = rectFromPoints(start, now);
    Object.assign(marquee.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.w}px`, height: `${rect.h}px` });
  };
  const up = (upEvent) => {
    const now = canvasPoint(upEvent.clientX, upEvent.clientY, canvasRect), rect = rectFromPoints(start, now); marquee.remove();
    const entries = rect.w < 4 && rect.h < 4 ? [] : $$(".region-tile").filter((tile) => {
      const left = Number.parseFloat(tile.style.left), top = Number.parseFloat(tile.style.top), width = Number.parseFloat(tile.style.width), height = Number.parseFloat(tile.style.height);
      return left < rect.x + rect.w && left + width > rect.x && top < rect.y + rect.h && top + height > rect.y;
    }).map((tile) => ({ image: state.images.find((item) => item.id === tile.dataset.imageId), region: state.images.find((item) => item.id === tile.dataset.imageId)?.regions.find((item) => item.id === tile.dataset.regionId) })).filter((item) => item.image && item.region);
    setSelection(entries); renderRegions(); renderInspector();
    window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function tilePoint(event, box, allowOutside = false) {
  const rect = box.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * 100, y = (event.clientY - rect.top) / rect.height * 100;
  return allowOutside ? [clamp(x, -10000, 10000), clamp(y, -10000, 10000)] : [clamp(x, 0, 100), clamp(y, 0, 100)];
}

function createTilePreview(box, kind) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("tile-draw-preview"); svg.setAttribute("viewBox", "0 0 100 100"); svg.dataset.previewKind = kind;
  box.appendChild(svg); return svg;
}

function startPolygonCut(event, box, { image, region }) {
  const points = [tilePoint(event, box, true)], svg = createTilePreview(box, "polygon");
  const underlay = document.createElementNS(svg.namespaceURI, "polyline"), shape = document.createElementNS(svg.namespaceURI, "polyline");
  underlay.classList.add("draw-preview-underlay"); shape.classList.add("draw-preview-line");
  svg.append(underlay, shape);
  const updatePreview = () => { const value = points.map((point) => point.join(",")).join(" "); underlay.setAttribute("points", value); shape.setAttribute("points", value); };
  updatePreview();
  const move = (moveEvent) => {
    const next = tilePoint(moveEvent, box, true), last = points[points.length - 1];
    if (Math.hypot(next[0] - last[0], next[1] - last[1]) < 1.2) return;
    points.push(next); updatePreview();
  };
  const up = (upEvent) => {
    const finalPoint = tilePoint(upEvent, box, true), last = points[points.length - 1];
    if (Math.hypot(finalPoint[0] - last[0], finalPoint[1] - last[1]) > .1) points.push(finalPoint);
    svg.remove(); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
    const raw = points.filter((point, index) => !index || Math.hypot(point[0] - points[index - 1][0], point[1] - points[index - 1][1]) > .15);
    const tileClipped = clipPolygonToTile(raw);
    if (tileClipped.length < 3 || polygonSelfIntersects(tileClipped)) return showToast("分区轨迹无法形成有效多边形，请重新绘制", "warn");
    const parentPolygon = regionPolygon(region).map(([x, y]) => [((Number(x) - Number(region.x)) / Number(region.w)) * 100, ((Number(y) - Number(region.y)) / Number(region.h)) * 100]);
    const clippedParts = intersectSimplePolygons(tileClipped, parentPolygon);
    if (!clippedParts.length) return showToast("绘制区域与当前模型多边形没有交集", "warn");
    const polygons = clippedParts.map((part) => part.map(([x, y]) => [+(Number(region.x) + x * Number(region.w) / 100).toFixed(3), +(Number(region.y) + y * Number(region.h) / 100).toFixed(3)]));
    if (polygons.some((polygon) => polygonArea(polygon) < .001 || polygonSelfIntersects(polygon))) return showToast("分区轨迹无法形成有效多边形，请重新绘制", "warn");
    pushHistory();
    const children = polygons.map((polygon) => makeManualPolygonRegion(image, region, polygon, "手动抠出"));
    region.holes = [...(region.holes || []), ...polygons.map((polygon) => ({ polygon }))]; region.cropSrc = null;
    image.regions.push(...children); setSelection(children.map((child) => ({ image, region: child }))); render();
    showToast(`多边形内容已从原块抠出为 ${children.length} 块；超出部分已沿模型边缘闭合`, "success");
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function clipPolygonToTile(points) {
  let output = points.map(([x, y]) => [x, y]);
  const edges = [
    { inside: ([x]) => x >= 0, intersect: (a, b) => [0, a[1] + (b[1] - a[1]) * (0 - a[0]) / ((b[0] - a[0]) || 1e-12)] },
    { inside: ([x]) => x <= 100, intersect: (a, b) => [100, a[1] + (b[1] - a[1]) * (100 - a[0]) / ((b[0] - a[0]) || 1e-12)] },
    { inside: ([, y]) => y >= 0, intersect: (a, b) => [a[0] + (b[0] - a[0]) * (0 - a[1]) / ((b[1] - a[1]) || 1e-12), 0] },
    { inside: ([, y]) => y <= 100, intersect: (a, b) => [a[0] + (b[0] - a[0]) * (100 - a[1]) / ((b[1] - a[1]) || 1e-12), 100] },
  ];
  for (const edge of edges) {
    if (!output.length) break;
    const input = output; output = [];
    let previous = input[input.length - 1], previousInside = edge.inside(previous);
    for (const current of input) {
      const currentInside = edge.inside(current);
      if (currentInside) {
        if (!previousInside) output.push(edge.intersect(previous, current));
        output.push(current);
      } else if (previousInside) output.push(edge.intersect(previous, current));
      previous = current; previousInside = currentInside;
    }
  }
  const compact = output.filter((point, index) => !index || Math.hypot(point[0] - output[index - 1][0], point[1] - output[index - 1][1]) > .15);
  if (compact.length > 2 && Math.hypot(compact[0][0] - compact[compact.length - 1][0], compact[0][1] - compact[compact.length - 1][1]) < .15) compact.pop();
  return compact;
}

function intersectSimplePolygons(subject, clip) {
  if (subject.length < 3 || clip.length < 3 || polygonSelfIntersects(subject) || polygonSelfIntersects(clip)) return [];
  const splits = (polygon) => polygon.map((point, index) => [{ t: 0, point }, { t: 1, point: polygon[(index + 1) % polygon.length] }]);
  const subjectSplits = splits(subject), clipSplits = splits(clip);
  const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
  for (let i = 0; i < subject.length; i++) {
    const a = subject[i], b = subject[(i + 1) % subject.length], r = [b[0] - a[0], b[1] - a[1]];
    for (let j = 0; j < clip.length; j++) {
      const c = clip[j], d = clip[(j + 1) % clip.length], s = [d[0] - c[0], d[1] - c[1]];
      const denominator = cross(r, s);
      if (Math.abs(denominator) < 1e-9) continue;
      const offset = [c[0] - a[0], c[1] - a[1]], t = cross(offset, s) / denominator, u = cross(offset, r) / denominator;
      if (t < -1e-8 || t > 1 + 1e-8 || u < -1e-8 || u > 1 + 1e-8) continue;
      const boundedT = clamp(t, 0, 1), point = [a[0] + r[0] * boundedT, a[1] + r[1] * boundedT];
      subjectSplits[i].push({ t: boundedT, point }); clipSplits[j].push({ t: clamp(u, 0, 1), point });
    }
  }
  const pointInOrOn = (point, polygon) => {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const a = polygon[j], b = polygon[i], edge = [b[0] - a[0], b[1] - a[1]], offset = [point[0] - a[0], point[1] - a[1]];
      if (Math.abs(cross(edge, offset)) < 1e-7 && point[0] >= Math.min(a[0], b[0]) - 1e-7 && point[0] <= Math.max(a[0], b[0]) + 1e-7 && point[1] >= Math.min(a[1], b[1]) - 1e-7 && point[1] <= Math.max(a[1], b[1]) + 1e-7) return true;
      if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / ((b[1] - a[1]) || 1e-12) + a[0]) inside = !inside;
    }
    return inside;
  };
  const keyOf = ([x, y]) => `${Math.round(x * 1e6)},${Math.round(y * 1e6)}`;
  const coordinates = new Map(), adjacency = new Map(), edges = new Set();
  const addEdge = (a, b) => {
    const from = keyOf(a), to = keyOf(b); if (from === to) return;
    coordinates.set(from, a); coordinates.set(to, b);
    const key = from < to ? `${from}|${to}` : `${to}|${from}`;
    if (edges.has(key)) return;
    edges.add(key);
    if (!adjacency.has(from)) adjacency.set(from, new Set());
    if (!adjacency.has(to)) adjacency.set(to, new Set());
    adjacency.get(from).add(to); adjacency.get(to).add(from);
  };
  const addContainedBoundary = (polygon, edgeSplits, other) => {
    for (let index = 0; index < polygon.length; index++) {
      const nodes = edgeSplits[index].sort((a, b) => a.t - b.t).filter((item, nodeIndex, all) => !nodeIndex || Math.abs(item.t - all[nodeIndex - 1].t) > 1e-8);
      for (let node = 0; node < nodes.length - 1; node++) {
        const a = nodes[node].point, b = nodes[node + 1].point, midpoint = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        if (pointInOrOn(midpoint, other)) addEdge(a, b);
      }
    }
  };
  addContainedBoundary(subject, subjectSplits, clip);
  addContainedBoundary(clip, clipSplits, subject);

  const used = new Set(), result = [];
  for (const firstEdge of edges) {
    if (used.has(firstEdge)) continue;
    const [start, first] = firstEdge.split("|");
    let previous = start, current = first, path = [start], closed = false;
    used.add(firstEdge);
    for (let step = 0; step <= edges.size + 1; step++) {
      if (current === start) { closed = true; break; }
      path.push(current);
      const options = [...(adjacency.get(current) || [])].filter((next) => {
        const key = current < next ? `${current}|${next}` : `${next}|${current}`;
        return !used.has(key);
      });
      if (!options.length) break;
      let next = options.find((candidate) => candidate !== previous) || options[0];
      const key = current < next ? `${current}|${next}` : `${next}|${current}`;
      used.add(key); previous = current; current = next;
    }
    if (!closed || path.length < 3) continue;
    const points = path.map((key) => coordinates.get(key));
    if (!points.some((point) => !point) && polygonArea(points) > .001 && !polygonSelfIntersects(points)) result.push(points);
  }
  return result;
}

function startRegionCover(event, box, { region }) {
  const start = tilePoint(event, box), svg = createTilePreview(box, "cover"), polygon = document.createElementNS(svg.namespaceURI, "polygon");
  svg.appendChild(polygon);
  const move = (moveEvent) => {
    const end = tilePoint(moveEvent, box), pts = [[start[0], start[1]], [end[0], start[1]], [end[0], end[1]], [start[0], end[1]]];
    polygon.setAttribute("points", pts.map((point) => point.join(",")).join(" "));
  };
  const up = (upEvent) => {
    const end = tilePoint(upEvent, box); svg.remove(); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
    if (Math.abs(end[0] - start[0]) < 1 || Math.abs(end[1] - start[1]) < 1) return;
    pushHistory(); region.whiteoutPolygons = region.whiteoutPolygons || [];
    region.whiteoutPolygons.push([[start[0], start[1]], [end[0], start[1]], [end[0], end[1]], [start[0], end[1]]]);
    region.cropSrc = null; render(); showToast("矩形覆盖已应用到选中内容块", "success");
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function startRegionBrush(event, box, { region }) {
  const points = [tilePoint(event, box)], rect = box.getBoundingClientRect(), svg = createTilePreview(box, "brush"), line = document.createElementNS(svg.namespaceURI, "polyline");
  line.setAttribute("stroke", "#fff"); line.setAttribute("stroke-width", String(Math.max(.6, 8 / rect.width * 100))); line.setAttribute("stroke-linecap", "round"); line.setAttribute("stroke-linejoin", "round");
  svg.appendChild(line); line.setAttribute("points", `${points[0][0]},${points[0][1]}`);
  const move = (moveEvent) => {
    const next = tilePoint(moveEvent, box), last = points[points.length - 1];
    if (Math.hypot(next[0] - last[0], next[1] - last[1]) < .5) return;
    points.push(next); line.setAttribute("points", points.map((point) => point.join(",")).join(" "));
  };
  const up = () => {
    svg.remove(); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
    pushHistory(); region.whiteoutPaths = region.whiteoutPaths || [];
    region.whiteoutPaths.push({ points, width: Math.max(.6, 8 / rect.width * 100) }); region.cropSrc = null;
    render(); showToast("画笔涂白已应用到选中内容块", "success");
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up, { once: true });
}

function makeManualPolygonRegion(image, parent, polygon, label) {
  const xs = polygon.map(([x]) => x), ys = polygon.map(([, y]) => y);
  const x = Math.min(...xs), y = Math.min(...ys), w = Math.max(...xs) - x, h = Math.max(...ys) - y;
  const imageScale = image.displayScale || Math.min(1, 760 / Math.max(1, image.sourceWidth || 760));
  const layoutW = Math.max(1, (image.sourceWidth || 760) * w / 100 * imageScale), layoutH = Math.max(1, (image.sourceHeight || 1000) * h / 100 * imageScale);
  const relX = (x - parent.x) / parent.w, relY = (y - parent.y) / parent.h;
  return { id: `manual-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`, label, kind: parent.kind, x, y, w, h, polygon, holes: structuredClone(parent.holes || []), group: parent.group, description: "从原内容块手工抠出的多边形区域", confidence: 1, cropSrc: null, layoutX: parent.layoutX + relX * parent.layoutW, layoutY: parent.layoutY + relY * parent.layoutH, layoutW, layoutH, homeLayoutX: (parent.homeLayoutX ?? parent.layoutX) + relX * parent.layoutW, homeLayoutY: (parent.homeLayoutY ?? 0) + relY * parent.layoutH, userMoved: true };
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
  delete image.syntheticRegion;
  delete image.homePageHeight;
  delete image.layoutPageY;
  image.regions = (result.regions || []).map((region, index) => ({ ...region, id: region.id || `region-${Date.now()}-${index}`, cropSrc: null, layoutX: null, layoutY: null, layoutW: null, layoutH: null, userMoved: false }));
  image.previewReady = false;
  image.analyzed = true;
  image.supervisionPending = !!result.jobId;
  image.supervisionJobId = result.jobId || null;
  image.supervisionUserEdited = false;
  state.lastAnalyzed = "刚刚";
  state.lastSupervision = result.supervision || null;
  if (state.currentId === image.id) setSelection(image.regions[0] ? [{ image, region: image.regions[0] }] : []);
  render();
}

async function waitForSupervision(jobId, initialResult) {
  if (!jobId) return initialResult;
  while (true) {
    const response = await fetch(`/api/segment-status?jobId=${encodeURIComponent(jobId)}`);
    if (!response.ok) throw new Error("监督任务暂时不可用");
    const result = await response.json();
    if (result.status === "complete") return { ...initialResult, regions: result.regions || initialResult.regions, source: "qwen-supervised", supervision: result.supervision || null, jobId: null };
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
}

async function segmentCurrent() {
  const image = currentImage(); if (!image) return showToast("请先选择一张图片", "warn");
  const button = $("#segmentButton"); button.disabled = true; button.innerHTML = '<span class="spinner"></span>正在理解语义…';
  setProcessingStatus("正在提交当前图片到 Qwen…");
  try {
    let result;
    if (image.src.startsWith("data:image/")) { const response = await fetch("/api/segment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: image.src, hint: "优先保持同一题目编号下的图片、图注和结构式完整" }) }); result = await response.json(); if (!response.ok) throw new Error(result.error || "分析失败"); }
    else { result = { regions: structuredClone(demoRegions), source: "offline" }; }
    if (result.jobId) { button.innerHTML = '<span class="spinner"></span>监督审校中…'; setProcessingStatus("初次分割完成，正在监督审校…"); result = await waitForSupervision(result.jobId, result); }
    applyAnalysisResult(image, result);
    setProcessingStatus("当前图片已完成最终分区");
    showToast(result.source === "qwen-supervised" ? `Qwen 分割 + 监督审校完成（${result.supervision?.rounds || 1} 轮）` : "已使用离线演示分区（可继续手动调整）", result.source === "qwen-supervised" ? "success" : "warn");
  } catch (error) { showToast(error.message || "分析失败，请稍后重试", "error"); }
  finally { button.disabled = false; button.innerHTML = "<span>✦</span>分析当前图片"; }
}

async function segmentSelectedRegion() {
  const image = currentImage();
  const parent = selectedRegion();
  if (!image || !parent || parent.synthetic) return showToast("请先选择一个可细分的内容块", "warn");
  if (parent.editAction === "delete") return showToast("删除标记的内容块不能细分；请先恢复为保留内容", "warn");
  const button = $("#splitRegionButton");
  const originalLabel = button.textContent;
  const geometryKey = JSON.stringify({ x: parent.x, y: parent.y, w: parent.w, h: parent.h, polygon: parent.polygon, holes: parent.holes });
  button.disabled = true;
  button.textContent = "正在分析此块…";
  setProcessingStatus("正在裁出选中块并进行局部分割…");
  try {
    const crop = parent.cropSrc || await cropRegion(image, parent);
    if (!crop.startsWith("data:image/")) throw new Error("该网页图片无法本地裁剪；请先重新导入图片");
    const response = await fetch("/api/segment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: crop,
        hint: "LOCAL REGION REFINEMENT: Split only the supplied crop into smaller independently editable semantic polygons. Return every visible mark and all content; do not delete, omit, or mark any child as delete. Preserve every word, stroke, symbol, and semantic unit. Give each child its true coordinates within this crop. The editor will map those coordinates back to the parent block and preserve their relative positions, so whitespace can collapse when the parent is replaced without deleting any content. Do not include crop boundaries or blank padding as regions.",
      }),
    });
    let result = await response.json();
    if (!response.ok) throw new Error(result.error || "局部分割失败");
    if (result.jobId) {
      button.textContent = "监督审校中…";
      setProcessingStatus("选中块初分完成，监督 agent 正在复核多边形与挖空…");
      result = await waitForSupervision(result.jobId, result);
    }
    if (result.source !== "qwen-supervised") {
      throw new Error(result.supervision?.issues?.[0] || "局部分割未通过多边形审校；原块保持不变");
    }
    if (!Array.isArray(result.regions) || result.regions.length < 2) {
      throw new Error("模型没有找到两个或更多子区域；原块保持不变");
    }
    const liveParent = image.regions.find((region) => region.id === parent.id);
    const liveGeometryKey = liveParent && JSON.stringify({ x: liveParent.x, y: liveParent.y, w: liveParent.w, h: liveParent.h, polygon: liveParent.polygon, holes: liveParent.holes });
    if (!liveParent || liveGeometryKey !== geometryKey) throw new Error("分析期间原块的裁剪范围已改变；请重新选择并分析");
    if (!image.sourceWidth || !image.sourceHeight) {
      const size = await imageSize(image.src);
      image.sourceWidth = size.width;
      image.sourceHeight = size.height;
      image.aspect = size.width / Math.max(1, size.height);
      image.displayScale = Math.min(1, 760 / Math.max(1, size.width));
    }
    if (!Number.isFinite(liveParent.layoutW) || !Number.isFinite(liveParent.layoutH)) initializeRegionLayout(liveParent, image);

    const children = result.regions.map((child, index) => {
      const polygon = child.polygon.map(([x, y]) => [
        +(liveParent.x + Number(x) * liveParent.w / 100).toFixed(3),
        +(liveParent.y + Number(y) * liveParent.h / 100).toFixed(3),
      ]);
      const xs = polygon.map(([x]) => x), ys = polygon.map(([, y]) => y);
      const x = Math.min(...xs), y = Math.min(...ys);
      const w = Math.max(...xs) - x, h = Math.max(...ys) - y;
      const holes = (child.holes || []).map((hole) => ({
        polygon: hole.polygon.map(([hx, hy]) => [
          +(liveParent.x + Number(hx) * liveParent.w / 100).toFixed(3),
          +(liveParent.y + Number(hy) * liveParent.h / 100).toFixed(3),
        ]),
      }));
      return {
        ...child,
        id: `${liveParent.id}.${child.id || `part-${index + 1}`}`,
        parentRegionId: liveParent.id,
        group: liveParent.group,
        x, y, w, h, polygon, holes,
        editAction: "keep",
        cropSrc: null,
        layoutX: liveParent.layoutX + Number(child.x) * liveParent.layoutW / 100,
        layoutY: liveParent.layoutY + Number(child.y) * liveParent.layoutH / 100,
        layoutW: Math.max(1, liveParent.layoutW * Number(child.w) / 100),
        layoutH: Math.max(1, liveParent.layoutH * Number(child.h) / 100),
        userMoved: true,
      };
    }).filter((child) => child.polygon.length >= 3 && child.w > 0 && child.h > 0);
    if (children.length < 2) throw new Error("审校结果不足两个有效子多边形；原块保持不变");

    pushHistory();
    const parentIndex = image.regions.findIndex((region) => region.id === liveParent.id);
    image.regions.splice(parentIndex, 1, ...children);
    image.previewReady = false;
    image.analyzed = true;
    if (state.currentId === image.id) state.selectedRegionId = children[0].id;
    state.lastAnalyzed = "刚刚";
    state.lastSupervision = result.supervision || null;
    render();
    setProcessingStatus(`已细分为 ${children.length} 个多边形块，并保留块内相对位置`);
    showToast(`内容块已细分为 ${children.length} 块；内容未删除，块内位置已保留`, "success");
  } catch (error) {
    setProcessingStatus("选中块细分未更改原分区");
    showToast(error.message || "局部分割失败", "error");
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

async function reanalyzeSelectedRegion() {
  const image = currentImage(), region = selectedRegion();
  if (!image || !region || region.synthetic) return showToast("请先选择一个可重分析的内容块", "warn");
  if (!image.src.startsWith("data:image/")) return showToast("原位重分析需要图片素材，请重新导入该图片", "warn");
  const button = $("#reanalyzeRegionButton"), previousLabel = button.textContent;
  const originalPolygon = regionPolygon(region).map(([x, y]) => [Number(x), Number(y)]);
  const geometryKey = JSON.stringify({ polygon: originalPolygon, holes: region.holes || [] });
  button.disabled = true; button.textContent = "正在独立重分析…";
  setProcessingStatus("正在把原图和当前多边形边界发送给重分析 agent…");
  try {
    const response = await fetch("/api/reanalyze-region", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: image.src, polygon: originalPolygon, label: region.label, kind: region.kind, group: region.group, description: region.description || "", editAction: region.editAction || "keep", holes: region.holes || [] }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "原位重分析失败");
    const liveRegion = image.regions.find((item) => item.id === region.id);
    if (!liveRegion || JSON.stringify({ polygon: regionPolygon(liveRegion), holes: liveRegion.holes || [] }) !== geometryKey) throw new Error("分析期间分区已更改，未应用重分析结果");
    pushHistory();
    if (!setRegionPolygon(image, liveRegion, result.polygon)) throw new Error("模型返回的多边形无效，原分区保持不变");
    liveRegion.cropSrc = null;
    setProcessingStatus("当前内容块已完成独立重分析");
    render(); showToast("已按当前原图重新分析并更新该块的多边形边界", "success");
  } catch (error) {
    setProcessingStatus("原位重分析未更改分区"); showToast(error.message || "原位重分析失败", "error");
  } finally { button.disabled = false; button.textContent = previousLabel; }
}

async function segmentAll() {
  const candidates = state.images.filter((image) => image.src.startsWith("data:image/") && !image.analyzed);
  if (!candidates.length) return showToast("队列中的图片都已分析，可继续人工调整", "warn");
  const batchButton = $("#segmentAllButton"); batchButton.disabled = true; batchButton.innerHTML = '<span class="spinner"></span>并发分析与审校中…';
  let finished = 0;
  setProcessingStatus("正在并发提交 " + candidates.length + " 张素材…");
  try {
    const results = await Promise.all(candidates.map(async (image) => {
      try {
        const response = await fetch("/api/segment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image: image.src, hint: "优先保持同一题目编号下的图片、图注和结构式完整" }) });
        let result = await response.json();
        if (!response.ok) throw new Error(result.error || "分析失败");
        if (result.jobId) { setProcessingStatus("已提交 " + candidates.length + " 张，等待监督审校（完成 " + finished + "/" + candidates.length + "）…"); result = await waitForSupervision(result.jobId, result); }
        applyAnalysisResult(image, result);
        finished += 1;
        setProcessingStatus("并发处理进度：完成 " + finished + "/" + candidates.length + " 张");
        return { ok: true };
      } catch {
        applyAnalysisResult(image, { regions: structuredClone(demoRegions), source: "offline", supervision: { status: "error", rounds: 0, audit: [] } });
        finished += 1;
        setProcessingStatus("并发处理进度：完成 " + finished + "/" + candidates.length + " 张");
        return { ok: false };
      }
    }));
    render(); setProcessingStatus("已完成 " + results.length + " 张图片的最终分区"); showToast(`已并发完成 ${results.length} 张图片的语义分区`, "success");
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
function drawPaint() { const canvas = $("#paintLayer"); if (!canvas.width) return; canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height); }

function clearWhiteouts() {
  const entries = selectedRegionEntries();
  if (entries.length !== 1) return showToast("请先单选一个要清除涂白的内容块", "warn");
  const { region } = entries[0];
  if (!(region.whiteoutPaths?.length || region.whiteoutPolygons?.length)) return showToast("当前内容块没有涂白或覆盖", "warn");
  pushHistory(); region.whiteoutPaths = []; region.whiteoutPolygons = []; region.cropSrc = null; render(); showToast("已清除当前内容块内的涂白", "success");
}
function deleteImage(imageId) {
  const index = state.images.findIndex((image) => image.id === imageId); if (index < 0) return;
  pushHistory(); state.images.splice(index, 1); delete state.whiteRects[imageId]; delete state.paintPaths[imageId];
  state.selectedRegionKeys = (state.selectedRegionKeys || []).filter((key) => !key.startsWith(`${imageId}::`));
  if (state.currentId === imageId) { const next = state.images[Math.min(index, state.images.length - 1)]; state.currentId = next?.id || null; state.selectedRegionId = next?.regions[0]?.id || null; state.selectedRegionKeys = next?.regions[0] ? [regionKey(next.id, next.regions[0].id)] : []; }
  render(); showToast("素材图片已删除", "success");
}
function deleteRegion(imageId, regionId) { const image = state.images.find((item) => item.id === imageId); if (!image) return; const region = image.regions.find((item) => item.id === regionId); if (!region) return; image.regions = image.regions.filter((item) => item.id !== regionId); }
function deleteSelected() {
  const entries = selectedRegionEntries(); if (!entries.length) return showToast("请先选择一个内容块", "warn");
  pushHistory(); entries.forEach(({ image, region }) => deleteRegion(image.id, region.id));
  setSelection([]); render(); showToast(`已移除 ${entries.length} 个内容块`, "success");
}

function saveProject() { const images = state.images.map((image) => ({ ...image, regions: image.regions.map(({ cropSrc, ...region }) => region), syntheticRegion: image.syntheticRegion ? (({ cropSrc, ...region }) => region)(image.syntheticRegion) : undefined })); const data = { version: 2, projectName: state.projectName, images, whiteRects: state.whiteRects, paintPaths: state.paintPaths, layoutWhiteRects: state.layoutWhiteRects, layoutPaintPaths: state.layoutPaintPaths, exportedAt: new Date().toISOString() }; const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = `${state.projectName || "draft-reformat"}.draft.json`; link.click(); URL.revokeObjectURL(link.href); showToast("项目 JSON 已保存", "success"); }

async function exportFinal() {
  if (!state.images.length) return showToast("请先加入图片素材", "warn");
  const button = $("#exportButton"); button.disabled = true; setProcessingStatus("正在生成终稿…"); showToast("正在整理分页，编号集合不会被拆开…", "success");
  try { const html = await buildExportHtml(); const output = window.open("", "_blank"); if (!output) throw new Error("浏览器拦截了预览窗口，请允许弹窗"); output.document.write(html); output.document.close(); setProcessingStatus("终稿预览已打开"); } catch (error) { setProcessingStatus("导出失败"); showToast(error.message || "导出失败", "error"); } finally { button.disabled = false; }
}

async function buildExportHtml() {
  const entries = [];
  const totalImages = state.images.length;
  let imageIndex = 0;
  let fallbackY = 28;
  for (const image of state.images) {
    imageIndex += 1;
    setProcessingStatus("正在裁剪第 " + imageIndex + "/" + totalImages + " 张素材…");
    if (!image.sourceWidth || !image.sourceHeight) {
      const size = await imageSize(image.src);
      image.sourceWidth = size.width;
      image.sourceHeight = size.height;
      image.aspect = size.width && size.height ? size.width / size.height : .72;
      image.displayScale = Math.min(1, 760 / Math.max(1, image.sourceWidth));
    }
    const keptRegions = image.regions.filter((region) => region.editAction !== "delete");
    const regions = keptRegions.length ? keptRegions : (image.regions.length ? [] : [image.syntheticRegion || { id: "full", label: image.name, kind: "other", x: 0, y: 0, w: 100, h: 100, group: "未分组", confidence: 1 }]);
    for (const region of regions) {
      const sourceWidth = image.sourceWidth || 760;
      const sourceHeight = image.sourceHeight || Math.round(sourceWidth / (image.aspect || .72));
      const scale = image.displayScale || Math.min(1, 760 / Math.max(1, sourceWidth));
      if (!Number.isFinite(region.layoutW) || !Number.isFinite(region.layoutH) || region.layoutW <= 0 || region.layoutH <= 0) {
        region.layoutW = Math.max(1, Math.round(sourceWidth * (Number(region.w) || 100) / 100 * scale));
        region.layoutH = Math.max(1, Math.round(sourceHeight * (Number(region.h) || 100) / 100 * scale));
      }
      if (!Number.isFinite(region.layoutX)) region.layoutX = 28;
      if (!Number.isFinite(region.layoutY)) region.layoutY = fallbackY;
      fallbackY = Math.max(fallbackY, region.layoutY + region.layoutH + 24);
      const group = state.keepGroups ? (region.group || region.id) : region.id;
      entries.push({ group, image, region, src: region.cropSrc || await cropRegion(image, region), order: entries.length });
    }
  }
  setProcessingStatus("正在按终端画布顺序整理集合分页…");
  entries.sort((a, b) => (a.region.layoutY || 0) - (b.region.layoutY || 0) || (a.region.layoutX || 0) - (b.region.layoutX || 0) || a.order - b.order);
  // A collection occupies one page. Collection order follows its first appearance
  // on the long terminal canvas, while blocks inside it retain their canvas coords.
  const collections = new Map();
  entries.forEach((entry) => {
    if (!collections.has(entry.group)) collections.set(entry.group, []);
    collections.get(entry.group).push(entry);
  });
  const pageGroups = [...collections.values()];
  const size = $("#pageSize").value;
  const dimensions = { a4: [794, 1123], a3: [1123, 1587], letter: [816, 1056] };
  const [pageWidth, pageHeight] = dimensions[size] || dimensions.a4;
  const pageMargin = clamp(Number($("#pageMargin").value), 0, Math.floor(Math.min(pageWidth, pageHeight) / 2));
  const pagesHtml = pageGroups.map((items) => {
    const groupTop = Math.min(...items.map((item) => item.region.layoutY || 0));
    const groupBottom = Math.max(...items.map((item) => (item.region.layoutY || groupTop) + (item.region.layoutH || 1)));
    const groupLeft = Math.min(...items.map((item) => Number.isFinite(item.region.layoutX) ? item.region.layoutX : 28));
    const groupRight = Math.max(...items.map((item) => (Number.isFinite(item.region.layoutX) ? item.region.layoutX : 28) + (item.region.layoutW || 1)));
    const contentWidth = Math.max(1, groupRight - groupLeft), contentHeight = Math.max(1, groupBottom - groupTop);
    const pageScale = Math.min(1, (pageWidth - pageMargin * 2) / contentWidth, (pageHeight - pageMargin * 2) / contentHeight);
    const groupHeight = Math.max(1, contentHeight * pageScale + pageMargin * 2);
    const blocksHtml = items.map((item) => {
      const region = item.region;
      const left = Math.max(0, Math.round(((Number.isFinite(region.layoutX) ? region.layoutX : 28) - groupLeft) * pageScale + pageMargin));
      const top = Math.max(0, Math.round(((Number.isFinite(region.layoutY) ? region.layoutY : groupTop) - groupTop) * pageScale + pageMargin));
      const width = Math.max(1, Math.round((Number.isFinite(region.layoutW) ? region.layoutW : 1) * pageScale));
      const height = Math.max(1, Math.round((Number.isFinite(region.layoutH) ? region.layoutH : 1) * pageScale));
      return '<article class="print-block" style="left:' + left + 'px;top:' + top + 'px;width:' + width + 'px;height:' + height + 'px"><img src="' + escapeHtml(item.src) + '" alt="' + escapeHtml(region.label || '') + '" style="width:' + width + 'px;height:' + height + 'px" /></article>';
    }).join('');
    return '<section class="print-page"><div class="print-group" data-group="' + escapeHtml(items[0].group) + '" style="height:' + groupHeight + 'px">' + blocksHtml + '</div></section>';
  }).join('');
  setProcessingStatus("正在打开纯内容 PDF 预览（" + pageGroups.length + " 页）…");
  const css = '@page{size:' + size + ' portrait;margin:0}' +
    '*{box-sizing:border-box}' +
    'html,body{margin:0;padding:0;background:#fff}' +
    '.print-page{width:' + pageWidth + 'px;height:' + pageHeight + 'px;min-height:' + pageHeight + 'px;margin:0;padding:0;overflow:hidden;background:#fff;page-break-after:always;break-after:page}' +
    '.print-group{position:relative;width:' + pageWidth + 'px;margin:0;padding:0;break-inside:avoid;page-break-inside:avoid}' +
    '.print-block{position:absolute;display:block;margin:0;padding:0;line-height:0;break-inside:avoid;page-break-inside:avoid}' +
    '.print-block img{display:block;max-width:none;max-height:none;object-fit:contain;object-position:left top;border:0;border-radius:0;background:#fff}' +
    '.print-overlays{position:absolute;inset:0;z-index:20;pointer-events:none;overflow:visible}' +
    '.print-whiteout{position:absolute;background:#fff}' +
    '.print-brush-overlays{position:absolute;inset:0;z-index:21;pointer-events:none;overflow:visible}' +
    '.print-brush-overlays polyline{fill:none;stroke:#fff;stroke-width:8;stroke-linecap:round;stroke-linejoin:round}' +
    '@media screen{.print-page{outline:1px solid #dfe2e8}}';
  return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' + escapeHtml(state.projectName) + ' · 终稿</title><style>' + css + '</style></head><body>' + pagesHtml + '<script>setTimeout(()=>window.print(),600)</script></body></html>';
}


function cropRegion(image, region) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const sourceWidth = img.naturalWidth || 760;
        const sourceHeight = img.naturalHeight || Math.round(sourceWidth / .72);
        const x = clamp(Number(region.x) || 0, 0, 100);
        const y = clamp(Number(region.y) || 0, 0, 100);
        const w = clamp(Number(region.w) || 100, 1, 100 - x);
        const h = clamp(Number(region.h) || 100, 1, 100 - y);
        const sx = sourceWidth * x / 100;
        const sy = sourceHeight * y / 100;
        const sw = Math.max(1, sourceWidth * w / 100);
        const sh = Math.max(1, sourceHeight * h / 100);
        const scale = Math.min(1, 1200 / Math.max(sw, sh));
        const width = Math.max(1, Math.round(sw * scale));
        const height = Math.max(1, Math.round(sh * scale));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, width, height);
        const polygon = Array.isArray(region.polygon) && region.polygon.length >= 3 ? region.polygon : null;
        ctx.save();
        if (polygon) {
          ctx.beginPath();
          polygon.forEach((point, index) => {
            const px = ((Number(point[0]) - x) / w) * width;
            const py = ((Number(point[1]) - y) / h) * height;
            index ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
          });
          ctx.closePath();
          ctx.clip();
        }
        ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height);
        ctx.restore();
        drawCropWhiteouts(ctx, image, region, width, height);
        (region.holes || []).forEach((hole) => drawCropHole(ctx, hole, region, width, height));
        resolve(canvas.toDataURL("image/png"));
      } catch {
        resolve(image.src);
      }
    };
    img.onerror = () => resolve(image.src);
    img.src = image.src;
  });
}

function drawCropHole(ctx, hole, region, width, height) {
  ctx.save();
  ctx.fillStyle = "#fff";
  if (!Array.isArray(hole?.polygon) || hole.polygon.length < 3) { ctx.restore(); return; }
  ctx.beginPath();
  hole.polygon.forEach((point, index) => {
    const px = ((Number(point[0]) - region.x) / region.w) * width;
    const py = ((Number(point[1]) - region.y) / region.h) * height;
    index ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  });
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawCropWhiteouts(ctx, image, region, width, height) {
  (region.whiteoutPolygons || []).forEach((polygon) => {
    if (!Array.isArray(polygon) || polygon.length < 3) return;
    ctx.fillStyle = "#fff"; ctx.beginPath();
    polygon.forEach(([x, y], index) => index ? ctx.lineTo(Number(x) / 100 * width, Number(y) / 100 * height) : ctx.moveTo(Number(x) / 100 * width, Number(y) / 100 * height));
    ctx.closePath(); ctx.fill();
  });
  (region.whiteoutPaths || []).forEach((path) => {
    if (!path.points?.length) return;
    ctx.strokeStyle = "#fff";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = Math.max(1, (Number(path.width) || 1) / 100 * width);
    ctx.beginPath();
    path.points.forEach(([x, y], index) => index ? ctx.lineTo(Number(x) / 100 * width, Number(y) / 100 * height) : ctx.moveTo(Number(x) / 100 * width, Number(y) / 100 * height));
    ctx.stroke();
  });
}


function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character])); }
function setProcessingStatus(message) { const node = $("#processingStatus"); if (node) node.textContent = message; }
function showToast(message, type = "success") { const toast = document.createElement("div"); toast.className = `toast ${type}`; toast.textContent = message; $("#toastStack").appendChild(toast); setTimeout(() => toast.remove(), 3400); }

init();
