/* Run with node --test test_app.cjs. No browser or Qwen credentials required. */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function editor() {
  const elements = new Map();
  const calls = [];
  const context = vm.createContext({
    console, structuredClone, setTimeout, clearTimeout, Map, Set,
    document: {
      querySelector(selector) {
        if (!elements.has(selector)) elements.set(selector, { value: selector === "#pageSize" ? "a4" : "0", innerHTML: "Agent", disabled: false, style: {}, classList: { toggle() {} } });
        return elements.get(selector);
      },
      querySelectorAll() { return []; },
      createElement(tag) {
        assert.equal(tag, "canvas");
        const draws = [];
        const canvas = { width: 0, height: 0, getContext() { return { fillRect(...args) { draws.push(["fill", ...args]); }, drawImage(...args) { draws.push(["image", ...args.slice(1)]); }, fillText() {} }; }, toDataURL() { calls.push({ width: this.width, height: this.height, draws }); return "data:image/png;base64,dGVzdA=="; } };
        return canvas;
      },
    },
  });
  vm.runInContext(fs.readFileSync("public/app.js", "utf8").replace(/\ninit\(\);\s*$/, ""), context);
  vm.runInContext("render = () => {}; showToast = () => {}; ensureImageMetrics = async () => {}; normalizeLongLayout = () => {}; loadCanvasImage = async () => ({naturalWidth: 100, naturalHeight: 50});", context);
  return { context, calls, run: (script) => vm.runInContext(script, context) };
}

function overlaps(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

test("compaction fixes collisions and giant gaps without altering crop sizes", () => {
  const { context, run } = editor();
  context.regions = [
    { id: "a", group: "Q2", layoutW: 220, layoutH: 100 },
    { id: "b", group: "Q2", layoutW: 180, layoutH: 100 },
    { id: "c", group: "Q3", layoutW: 740, layoutH: 200 },
  ];
  context.fixed = [{ region: { layoutX: 24, layoutY: 24, layoutW: 740, layoutH: 110, group: "Q1" } }];
  const before = JSON.stringify(context.regions);
  const placed = run("compactMaterialPlacements(regions, regions.map((r, order) => ({id:r.id,x:790,y:90000,order})), fixed)");
  assert.equal(placed[0].y, 150);
  assert.ok(placed[2].y < 500);
  assert.equal(JSON.stringify(context.regions), before);
  const all = [{ x: 24, y: 24, w: 740, h: 110 }, ...placed];
  all.forEach((a, i) => { assert.ok(a.x >= 24 && a.x + a.w <= 800); all.slice(i + 1).forEach((b) => assert.equal(overlaps(a, b), false)); });
});

test("PDF HTML and layout rasters use identical page rectangles and intact groups", async () => {
  const { context, calls, run } = editor();
  context.entries = [
    { group: "Q1", image: { id: "img" }, region: { id: "a", layoutX: 28, layoutY: 28, layoutW: 100, layoutH: 50 }, src: "crop", order: 0 },
    { group: "Q2", image: { id: "img" }, region: { id: "b", layoutX: 28, layoutY: 200, layoutW: 600, layoutH: 900 }, src: "crop", order: 1 },
    { group: "Q3", image: { id: "img" }, region: { id: "c", layoutX: 28, layoutY: 1300, layoutW: 400, layoutH: 180 }, src: "crop", order: 2 },
  ];
  run("collectExportEntries = async () => entries; const plan = createExportPlan(entries, {size:'a4',margin:0}); globalThis.plan = plan;");
  assert.equal(context.plan.pages.length, 2);
  assert.equal(context.plan.pages[0].blocks.length, 2);
  assert.equal(context.plan.pages[0].blocks[0].width, 100);
  const html = await run("buildExportHtml()");
  const page = context.plan.pages[0];
  await run("rasterizeExportPage(plan.pages[0], plan)");
  assert.equal(calls.length, 1);
  page.blocks.forEach((block, index) => {
    assert.ok(html.includes(`left:${block.left}px;top:${block.top}px;width:${block.width}px;height:${block.height}px`));
    const draw = calls[0].draws.filter((item) => item[0] === "image")[index];
    assert.equal(draw[1], block.left); assert.equal(draw[2], block.top);
    assert.ok(draw[3] <= block.width && draw[4] <= block.height);
  });
});

test("compaction preserves an agent's separate caption row while closing excessive whitespace", () => {
  const { context, run } = editor();
  context.regions = [{id:"figure",group:"Q1",layoutW:250,layoutH:100},{id:"caption",group:"Q1",layoutW:200,layoutH:40}];
  const placed = run("compactMaterialPlacements(regions,[{id:'figure',x:24,y:24,order:0},{id:'caption',x:24,y:7000,order:1}],[])");
  assert.equal(placed[0].y, 24);
  assert.equal(placed[1].y, 136);
  assert.equal(placed[1].x, 24);
});

test("each material request follows application and fresh rendering of the previous result", async () => {
  const { context, run } = editor();
  context.requests = [];
  context.views = [];
  run(`
    state.images = [1,2,3].map((n) => ({id:'img'+n,name:'source'+n,src:'data:image/png;base64,eA==',regions:[{id:'r'+n,group:'Q'+n,label:'text',layoutX:28,layoutY:n*5000,layoutW:740,layoutH:100,userMoved:true}]}));
    buildLayoutViews = async (image, fixed) => {
      views.push({imageId:image.id,fixed:fixed.map(({region})=>({id:region.id,x:region.layoutX,y:region.layoutY})), positions:state.images.map(i=>i.regions[0].layoutY)});
      return [{kind:'pdf-page',image:'fresh-'+views.length},{kind:'crop-sheet',image:'crops'}];
    };
    fetch = async (path, options) => {
      const payload = JSON.parse(options.body); requests.push(payload);
      if (requests.length > 1) {
        if (payload.layoutContext.fixedBlocks.length !== requests.length-1) throw Error('previous step not applied');
        if (payload.layoutContext.fixedBlocks.some(r=>r.y>1000)) throw Error('large stale gap');
      }
      return {ok:true,json:async()=>({placements:payload.regions.map((r,order)=>({id:r.id,imageId:r.imageId,x:790,y:90000,order}))})};
    };
  `);
  await run("autoLayoutWithAgent()");
  assert.equal(context.requests.length, 3);
  context.requests.forEach((request, index) => {
    assert.equal(request.regions.length, 1);
    assert.equal(request.regions[0].imageId, `img${index + 1}`);
    assert.equal(request.layoutContext.step, index + 1);
    assert.equal(request.layoutViews[0].image, `fresh-${index + 1}`);
  });
  assert.equal(context.views[1].fixed[0].y, 24);
  assert.deepEqual(JSON.parse(run("JSON.stringify(state.images.map(i=>i.regions[0].layoutY))")), [24, 140, 256]);
  assert.equal(run("state.history.length"), 1);
  run("undo()");
  assert.deepEqual(JSON.parse(run("JSON.stringify(state.images.map(i=>i.regions[0].layoutY))")), [5000, 10000, 15000]);
});

test("pending materials move behind compacted results, including whole unanalysed sources", () => {
  const { context, run } = editor();
  run(`state.images = [
    {id:'img1',regions:[{id:'r1',group:'Q1',layoutX:24,layoutY:24,layoutW:740,layoutH:100}]},
    {id:'img2',regions:[],syntheticRegion:{id:'whole',group:'—',layoutX:24,layoutY:90000,layoutW:740,layoutH:400}}
  ]; reflowPendingMaterials([state.images[1]],[{image:state.images[0],region:state.images[0].regions[0]}]);`);
  assert.equal(run("state.images[1].syntheticRegion.layoutY"), 140);
  assert.equal(run("state.images[1].syntheticRegion.layoutH"), 400);
});

test("a right-column caption fills space under its figure beside a taller left column", () => {
  const { context, run } = editor();
  context.regions = [{id:"left",group:"Q1",layoutW:300,layoutH:300},{id:"right",group:"Q1",layoutW:280,layoutH:180},{id:"caption",group:"Q1",layoutW:280,layoutH:50}];
  const placed = run("compactMaterialPlacements(regions,[{id:'left',x:24,y:24,order:0},{id:'right',x:336,y:24,order:1},{id:'caption',x:336,y:220,order:2}],[])");
  assert.equal(placed[1].y, 24);
  assert.equal(placed[2].y, 216);
  assert.equal(placed[2].x, 336);
});
