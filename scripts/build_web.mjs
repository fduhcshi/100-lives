import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { createPagesDemo } from "./pages_demo.mjs";

const root = new URL("../", import.meta.url).pathname;
const staticDir = join(root, "static");
const cloudPublic = join(root, "cloudflare", "public");
const pages = join(root, "docs", "pages");

await rm(cloudPublic, { recursive: true, force: true });
await mkdir(join(cloudPublic, "static"), { recursive: true });
await cp(staticDir, join(cloudPublic, "static"), { recursive: true });
await cp(join(staticDir, "index.html"), join(cloudPublic, "index.html"));
await cp(join(staticDir, "result.html"), join(cloudPublic, "result.html"));

await rm(pages, { recursive: true, force: true });
await mkdir(join(pages, "static"), { recursive: true });
await cp(join(staticDir, "style.css"), join(pages, "static", "style.css"));
await cp(join(staticDir, "pages.js"), join(pages, "static", "pages.js"));
await cp(join(staticDir, "result.js"), join(pages, "static", "result.js"));

const resultTemplate = await readFile(join(staticDir, "result.html"), "utf8");
const reportStart = resultTemplate.indexOf('<main id="result-main"');
const modalStart = resultTemplate.indexOf('  <!-- 轨迹弹窗', reportStart);
const scriptStart = resultTemplate.indexOf('  <script src="/static/result.js"', modalStart);
if (reportStart < 0 || modalStart < 0 || scriptStart < 0) throw new Error("找不到报告页面结构");

const report = resultTemplate.slice(reportStart, modalStart).trim()
  .replace('<main id="result-main" class="wrap" style="display: none;">', '<section id="result-main" class="wrap pages-demo-report" style="display: none;">')
  .replace(/<\/main>\s*$/, "</section>")
  .replace('href="/">← 返回首页', 'href="#form-section">↑ 返回输入区')
  .replace('点击卡片查看完整时间线，并可与未来的自己对话', '点击卡片查看完整时间线');
const dialogs = resultTemplate.slice(modalStart, scriptStart);
const scriptJson = JSON.stringify(createPagesDemo()).replace(/[<>&\u2028\u2029]/g, char => ({
  "<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029",
})[char]);
const demo = `
<section class="wrap pages-demo-intro" id="demo-report" aria-labelledby="demo-title">
  <div class="pages-demo-banner">
    <span class="pages-demo-label">完整示例报告 · 继续向下浏览</span>
    <h2 id="demo-title">陶艺，还是摄影？看看两条路如何展开</h2>
    <p>以下是手工编写的虚构示例，供你体验完整报告与交互。上方输入不会生成新报告；GitHub Pages 不调用 AI。</p>
  </div>
</section>
<div id="loading" hidden></div><div id="not-found" hidden></div>
${report}
${dialogs}
<style>
  .pages-demo-intro { margin-top: 76px; }
  .pages-demo-banner { padding: 26px 30px; border: 2px solid var(--ink); border-radius: var(--radius-lg); box-shadow: var(--shadow-md); background: var(--surface); }
  .pages-demo-label { color: var(--warn); font-size: 13px; font-weight: 800; letter-spacing: .04em; }
  .pages-demo-banner h2 { margin: 8px 0; font-size: clamp(24px, 3vw, 36px); }
  .pages-demo-banner p { margin: 0; }
  .pages-demo-report { padding-top: 12px; padding-bottom: 70px; }
  .pages-demo-report #download-report, .pages-demo-report footer { display: none; }
</style>
<script>window.__100_LIVES_RESULT__=${scriptJson};window.__100_LIVES_STANDALONE__=true;window.__100_LIVES_PAGES_DEMO__=true;</script>
<script src="./static/result.js" defer></script>
`;
const index = (await readFile(join(staticDir, "index.html"), "utf8"))
  .replaceAll('href="/static/', 'href="./static/')
  .replace('src="/static/app.js"', 'src="./static/pages.js"')
  .replace('</main>', `</main>${demo}`);
await writeFile(join(pages, "index.html"), index);
await writeFile(join(pages, ".nojekyll"), "");
