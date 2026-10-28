import { copyFile, mkdir, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const sourceDir = path.resolve("node_modules/@fontsource/vazirmatn/files");
const destinationDir = path.resolve("astrostore/static/fonts");
const cssPath = path.resolve("astrostore/static/css/fonts.css");
const weights = [400, 500, 600, 700];
const available = await readdir(sourceDir);
const rules = [];

await mkdir(destinationDir, { recursive: true });
for (const weight of weights) {
  const file = available.find((name) => name === `vazirmatn-arabic-${weight}-normal.woff2`);
  if (!file) throw new Error(`Missing Vazirmatn Arabic font file for weight ${weight}.`);
  await copyFile(path.join(sourceDir, file), path.join(destinationDir, file));
  rules.push(`@font-face{font-family:Vazirmatn;font-style:normal;font-weight:${weight};font-display:swap;src:url("/static/fonts/${file}") format("woff2");unicode-range:U+0600-06FF,U+0750-077F,U+08A0-08FF,U+FB50-FDFF,U+FE70-FEFF}`);
}
await writeFile(cssPath, `${rules.join("\n")}\n`, "utf8");
