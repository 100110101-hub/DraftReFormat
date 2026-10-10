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
    requestAnimationFrame: (callback) => setTimeout(callback, 0),
    document: {
      querySelector(selector) {
        if (!elements.has(selector)) elements.set(selector, { value: selector === "#pageSize" ? "a4" : "0", innerHTML: "Agent", disabled: false, style: {}, scrollTop: 0, clientHeight: 500, setAttribute() {}, classList: { toggle() {} } });
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
  context.fixed = [{ region: { layoutX: 0, layoutY: 0, layoutW: 800, layoutH: 110, group: "Q1" } }];
  const before = JSON.stringify(context.regions);
  const placed = run("compactMaterialPlacements(regions, regions.map((r, order) => ({id:r.id,x:790,y:90000,order})), fixed)");
  assert.equal(placed[0].y, 110);
  assert.ok(placed[2].y < 500);
  assert.equal(JSON.stringify(context.regions), before);
  const all = [{ x: 0, y: 0, w: 800, h: 110 }, ...placed];
  all.forEach((a, i) => { assert.ok(a.x >= 0 && a.x + a.w <= 800); all.slice(i + 1).forEach((b) => assert.equal(overlaps(a, b), false)); });
});

test("PDF HTML and layout rasters use identical page rectangles and intact groups", async () => {
  const { context, calls, run } = editor();
  context.entries = [
    { group: "Q1", image: { id: "img" }, region: { id: "a", layoutX: 28, layoutY: 28, layoutW: 100, layoutH: 50 }, src: "crop", order: 0 },
    { group: "Q2", image: { id: "img" }, region: { id: "b", layoutX: 28, layoutY: 200, layoutW: 600, layoutH: 900 }, src: "crop", order: 1 },
    { group: "Q3", image: { id: "img" }, region: { id: "c", layoutX: 28, layoutY: 1300, layoutW: 400, layoutH: 180 }, src: "crop", order: 2 },
  ];
  run("collectExportEntries = async () => entries; const plan = createExportPlan(entries, {size:'a4',margin:120}); globalThis.plan = plan;");
  assert.equal(context.plan.pages.length, 2);
  assert.equal(context.plan.pages[0].blocks.length, 2);
  assert.equal(context.plan.pages[0].blocks[0].width, 100);
  assert.equal(context.plan.pageMargin, 0);
  assert.equal(context.plan.pages[0].blocks[0].left, 0);
  assert.equal(context.plan.pages[0].blocks[0].top, 0);
  assert.equal(context.plan.pages[0].blocks[1].top, 50);
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
  const placed = run("compactMaterialPlacements(regions,[{id:'figure',x:0,y:0,order:0},{id:'caption',x:0,y:7000,order:1}],[])");
  assert.equal(placed[0].y, 0);
  assert.equal(placed[1].y, 100);
  assert.equal(placed[1].x, 0);
});

test("each region, including regions from the same source, gets a request after the previous result is painted", async () => {
  const { context, run } = editor();
  context.requests = [];
  context.views = [];
  run(`
    const blocks = [1,2,3].map(n=>({id:'r'+n,group:'Q1',label:'text',layoutX:0,layoutY:n*5000,layoutW:800,layoutH:100,userMoved:true}));
    state.images = [{id:'img1',name:'source1',src:'data:image/png;base64,eA==',regions:blocks.slice(0,2)}, {id:'img2',name:'source2',src:'data:image/png;base64,eA==',regions:blocks.slice(2)}];
    state.canvasLocked = true;
    const paintStep = displayLayoutStep;
    globalThis.paints = [];
    displayLayoutStep = async region => { await paintStep(region); paints.push(region.id); };
    buildLayoutViews = async ({image,region}, fixed) => {
      if (views.length && paints.length !== views.length) throw Error('previous result not painted');
      views.push({imageId:image.id,regionId:region.id,fixed:fixed.map(({region})=>({id:region.id,x:region.layoutX,y:region.layoutY})), positions:state.images.flatMap(i=>i.regions.map(r=>r.layoutY))});
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
    assert.equal(request.regions[0].imageId, index < 2 ? "img1" : "img2");
    assert.equal(request.regions[0].id, `r${index + 1}`);
    assert.equal(request.layoutContext.step, index + 1);
    assert.equal(request.layoutViews[0].image, `fresh-${index + 1}`);
  });
  assert.equal(context.views[1].fixed[0].y, 0);
  assert.deepEqual(JSON.parse(run("JSON.stringify(state.images.flatMap(i=>i.regions.map(r=>r.layoutY)))")), [0, 100, 200]);
  assert.deepEqual(Array.from(context.paints), ["r1", "r2", "r3"]);
  assert.equal(run("state.selectedRegionId"), "r3");
  assert.equal(run("state.canvasLocked"), true);
  assert.equal(run("state.agentLayoutRunning"), false);
  assert.equal(run("state.history.length"), 1);
  run("state.canvasLocked=false; undo()");
  assert.deepEqual(JSON.parse(run("JSON.stringify(state.images.flatMap(i=>i.regions.map(r=>r.layoutY)))")), [5000, 10000, 15000]);
});

test("pending regions move behind fixed content, including whole unanalysed sources", () => {
  const { context, run } = editor();
  run(`state.images = [
    {id:'img1',regions:[{id:'r1',group:'Q1',layoutX:0,layoutY:0,layoutW:800,layoutH:100}]},
    {id:'img2',regions:[],syntheticRegion:{id:'whole',group:'—',layoutX:0,layoutY:90000,layoutW:740,layoutH:400}}
  ]; reflowPendingRegions([{image:state.images[1],region:state.images[1].syntheticRegion}],[{image:state.images[0],region:state.images[0].regions[0]}]);`);
  assert.equal(run("state.images[1].syntheticRegion.layoutY"), 100);
  assert.equal(run("state.images[1].syntheticRegion.layoutH"), 400);
});

test("a right-column caption fills space under its figure beside a taller left column", () => {
  const { context, run } = editor();
  context.regions = [{id:"left",group:"Q1",layoutW:300,layoutH:300},{id:"right",group:"Q1",layoutW:280,layoutH:180},{id:"caption",group:"Q1",layoutW:280,layoutH:50}];
  const placed = run("compactMaterialPlacements(regions,[{id:'left',x:0,y:0,order:0},{id:'right',x:300,y:0,order:1},{id:'caption',x:300,y:220,order:2}],[])");
  assert.equal(placed[1].y, 0);
  assert.equal(placed[2].y, 180);
  assert.equal(placed[2].x, 300);
});

test("restoring holes recovers source pixels, merges linked children and supports undo", () => {
  const { run } = editor();
  run(`state.images=[{id:'img',regions:[
    {id:'parent',holes:[{polygon:[[1,1],[2,1],[1,2]],extractedRegionId:'child'}, {polygon:[[3,3],[4,3],[3,4]],extractedRegionId:'deleted-child'}],cropSrc:'masked',whiteoutPaths:[{points:[[1,1],[2,2]]}]},
    {id:'child'}, {id:'unrelated'}
  ]}]; state.currentId='img'; state.selectedRegionId='parent';`);
  run("restoreRegionHoles(0)");
  assert.equal(run("selectedRegion().holes.length"), 1);
  assert.equal(run("selectedRegion().cropSrc"), null);
  assert.equal(run("selectedRegion().whiteoutPaths.length"), 1);
  assert.equal(run("state.images[0].regions.some(r=>r.id==='child')"), false);
  assert.equal(run("state.images[0].regions.some(r=>r.id==='unrelated')"), true);
  run("restoreRegionHoles()");
  assert.equal(run("selectedRegion().holes.length"), 0);
  run("undo(); undo()");
  assert.equal(run("selectedRegion().holes.length"), 2);
  assert.equal(run("state.images[0].regions.some(r=>r.id==='child')"), true);
});

test("canvas lock prevents manual edits, recovery, deletion and undo", () => {
  const { run } = editor();
  run(`state.images=[{id:'img',regions:[{id:'r',label:'original',holes:[{polygon:[[1,1],[2,1],[1,2]]}]}]}]; state.currentId='img'; state.selectedRegionId='r'; state.canvasLocked=true; globalThis.before=snapshot();
    updateSelected('label','changed'); restoreRegionHoles(); deleteSelected(); deleteImage('img'); undo();`);
  assert.equal(run("snapshot()"), run("before"));
  assert.equal(run("state.history.length"), 0);
});

test("sequential compaction fills a caption under the last right-hand figure", () => {
  const { context, run } = editor();
  context.fixed = [
    {region:{layoutX:0,layoutY:0,layoutW:300,layoutH:300,group:'Q1'}},
    {region:{layoutX:300,layoutY:0,layoutW:280,layoutH:180,group:'Q1'}},
  ];
  const placed = run("compactMaterialPlacements([{id:'caption',group:'Q1',layoutW:280,layoutH:50}],[{id:'caption',x:300,y:180,order:0}],fixed)");
  assert.equal(placed[0].x, 300);
  assert.equal(placed[0].y, 180);
});

test("a failed region request retains completed regions and unlocks editing", async () => {
  const { run } = editor();
  run(`state.images = [{id:'img',name:'source',src:'data:image/png;base64,eA==',regions:[1,2].map(n=>({id:'r'+n,label:'text',group:'Q1',layoutX:0,layoutY:n*5000,layoutW:800,layoutH:100,userMoved:true}))}];
    buildLayoutViews=async()=>[]; let count=0;
    fetch=async(path,options)=>{const r=JSON.parse(options.body).regions[0]; return ++count===1 ? {ok:true,json:async()=>({placements:[{id:r.id,imageId:r.imageId,x:0,y:0,order:0}]})} : {ok:false,json:async()=>({error:'Test failure'})};};`);
  await run("autoLayoutWithAgent()");
  assert.equal(run("state.agentLayoutRunning"), false);
  assert.equal(run("isCanvasLocked()"), false);
  assert.equal(run("state.images[0].regions[0].layoutY"), 0);
  assert.equal(run("state.images[0].regions[1].layoutY"), 100);
  assert.match(run("$('#processingStatus').textContent"), /完成 1\/2 个分区/);
  run("undo()");
  assert.equal(run("state.images[0].regions[0].layoutY"), 5000);
});

test("selecting and removing an unanalysed whole-image block is undoable", () => {
  const { run } = editor();
  run("state.images=[{id:'img',regions:[],syntheticRegion:{id:'whole',synthetic:true}}]; state.currentId='img'; state.selectedRegionId='whole'; deleteSelected()");
  assert.equal(run("state.images.length"), 0);
  assert.equal(run("state.history.length"), 1);
  run("undo()");
  assert.equal(run("selectedRegion().id"), "whole");
});
