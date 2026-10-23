// Build the checked-in Tailwind 3 stylesheet using an immutable upstream CLI.
// The standalone distribution avoids Tailwind's vulnerable npm globbing toolchain.
import { createHash, randomUUID } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, renameSync, chmodSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)));
const VERSION = "v3.4.19";
// SHA256 digests are from the upstream GitHub release asset metadata.
const ASSETS = Object.freeze({
  "linux-x64": ["tailwindcss-linux-x64", "4af3198c015616ea7d6617974ec3d70d987ecc00c1ca8463b0a30fd65cc7c06e"],
  "linux-arm64": ["tailwindcss-linux-arm64", "e5b2d27694daa80cc52ec29553ba2c6bd43d86bd51a9d633ed24058b9c05a676"],
  "darwin-x64": ["tailwindcss-macos-x64", "a597f407e0f1f03535731f5b42f1576a8152cb5fffc2f38e754722bc0c280045"],
  "darwin-arm64": ["tailwindcss-macos-arm64", "7fdeb00818b6214a337383063282b2361ecb08bbc08f8c8a7ba97ee1e2eaa4fe"],
  "win32-x64": ["tailwindcss-windows-x64.exe", "a15158c4c5e0e7a75f7229bfe4986fe7710d2edc468b6f96c8981f78ab211347"],
  "win32-arm64": ["tailwindcss-windows-arm64.exe", "f2b6b999747aa0ae31999d59db117b1ba1e4e15e17675d7108e30aac4b680686"]
});

const digest = (data) => createHash("sha256").update(data).digest("hex");
const selected = ASSETS[process.platform + "-" + process.arch];
if (!selected) {
  process.stderr.write("Tailwind standalone CLI is not published for " + process.platform + "/" + process.arch + "\n");
  process.exit(1);
}

const [asset, expected] = selected;
const dir = join(homedir(), ".cache", "huntx", "tailwind", VERSION);
const binary = join(dir, asset);
const source = "https://github.com/tailwindlabs/tailwindcss/releases/download/" + VERSION + "/" + asset;

async function ensureBinary() {
  mkdirSync(dir, { recursive: true });
  if (existsSync(binary) && digest(readFileSync(binary)) === expected) {
    chmodSync(binary, 0o755);
    return;
  }
  // Fetch the official release asset, but trust only its pinned checksum.
  const response = await fetch(source, { signal: AbortSignal.timeout(120000) });
  if (!response.ok) throw new Error("Tailwind CLI download failed: HTTP " + response.status);
  const content = Buffer.from(await response.arrayBuffer());
  if (digest(content) !== expected) throw new Error("Tailwind CLI SHA256 mismatch for " + asset);
  const temp = binary + "." + randomUUID() + ".tmp";
  try {
    writeFileSync(temp, content, { mode: 0o755, flag: "wx" });
    renameSync(temp, binary);
  } finally {
    if (existsSync(temp)) unlinkSync(temp);
  }
  chmodSync(binary, 0o755);
}

try {
  await ensureBinary();
  const result = spawnSync(binary, [
    "-i", "docs/assets/css/input.css",
    "-o", "docs/assets/css/tailwind.css",
    "--minify"
  ], { cwd: ROOT, stdio: "inherit", timeout: 120000 });
  if (result.error) throw result.error;
  process.exit(result.status ?? 1);
} catch (error) {
  process.stderr.write("Tailwind CSS build failed: " + error.message + "\n");
  process.exit(1);
}
