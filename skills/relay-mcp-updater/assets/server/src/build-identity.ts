import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
export function buildIdentity(): string {
  const files: string[] = [];
  for (const root of ["dist", "src/public"]) {
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const file = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(file);
        else if (entry.isFile() && file.endsWith(".js")) files.push(file);
      }
    };
    walk(root);
  }
  files.push("package-lock.json");
  const hash = crypto.createHash("sha256");
  for (const file of files.sort()) {
    hash.update(file.split(path.sep).join("/") + "\0");
    hash.update(fs.readFileSync(file));
    hash.update("\0");
  }
  return hash.digest("hex");
}
