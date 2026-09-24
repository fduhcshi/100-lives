import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";

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
const index = (await readFile(join(staticDir, "index.html"), "utf8"))
  .replaceAll('href="/static/', 'href="./static/')
  .replace('src="/static/app.js"', 'src="./static/pages.js"');
await writeFile(join(pages, "index.html"), index);
await writeFile(join(pages, ".nojekyll"), "");
