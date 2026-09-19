function test(name, run) { run(); console.log('PASS ' + name); }
const assert = require('assert').strict;
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../static/result.js'), 'utf8');
test('all report sections share one visible page without mode navigation', () => {
  const html = fs.readFileSync(path.join(__dirname, '../static/result.html'), 'utf8');
  assert.ok(html.includes('<div id="full-report">'));
  [1,2,3].forEach(id => assert.ok(html.includes('id="explore-' + id + '"')));
  assert.ok(!/mode-story|mode-full|story-next|story-prev/.test(html + source));
});
// Execute the real pure helpers without a browser, network or model calls.
function helpers(weights = [20,20,20,20,20], DATA = {}) {
  const context = { weights, DATA, TRAJ_SCORES: ['a','b','c','d','r'].map(key => ({key})) };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function weightedScore('), source.indexOf('  function storyTitle(')), context);
  return context;
}
test('equal weights reverse regret and reject missing scores', () => {
  const h = helpers();
  assert.equal(h.weightedScore([80,70,60,50,20]), 68);
  assert.equal(h.weightedScore([80,70,60,null,20]), null);
  assert.equal(h.weightedScore([80,70,60,NaN,20]), null);
});
test('custom preference and all-zero protection', () => {
  assert.equal(helpers([100,0,0,0,0]).weightedScore([80,70,60,50,20]), 80);
  assert.equal(helpers([0,0,0,0,100]).weightedScore([80,70,60,50,20]), 80);
  assert.equal(helpers([0,0,0,0,0]).weightedScore([80,70,60,50,20]), null);
});
test('paired worlds preserve missing outcomes and close boundary', () => {
  const t = (id, choice, score) => ({universe_id:id, choice, a:score,b:score,c:score,d:score,r:100-score});
  const h = helpers(undefined, {universes:[{id:1},{id:2},{id:3},{id:4}], trajectories:[t(1,'A',80),t(1,'B',77),t(2,'A',80),t(2,'B',76),t(3,'B',90)]});
  assert.equal(h.pairs().length, 4);
  assert.equal(JSON.stringify(h.counts(-1)), JSON.stringify({A:1,B:0,close:1,missing:2}));
  assert.equal(h.trajectoryScore({r:10},4),90);
  assert.equal(h.trajectoryScore(null,0),null);
});
