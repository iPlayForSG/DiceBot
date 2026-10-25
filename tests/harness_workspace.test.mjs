import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, writeFile, symlink, rm } from "node:fs/promises";

const project = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const runtime = path.join(project, ".local-tools/harness");
const installed = existsSync(
  path.join(runtime, "node_modules/@deepseek-ai/dsh-tools/lib/index.js"),
);

test(
  "Harness workspace tools enforce physical file boundaries",
  { skip: !installed },
  async (t) => {
    process.env.DICEBOT_HARNESS_PACKAGE_ROOT = runtime;
    const { readWorkspace, listWorkspace } = await import(
      "../harness_bridge/workspace-tools.mjs"
    );
    const temporary = await mkdtemp(
      path.join(os.tmpdir(), "dicebot-harness-tools-"),
    );
    const workspace = path.join(temporary, "workspace");
    const outside = path.join(temporary, "outside");
    await mkdir(workspace);
    await mkdir(outside);
    await writeFile(path.join(workspace, "notes.txt"), "允许读取的资料");
    await writeFile(
      path.join(outside, "private.txt"),
      "test-only outside data",
    );
    try {
      await t.test(
        "reads allowed text and lists only the workspace",
        async () => {
          assert.equal(
            await readWorkspace(workspace, "notes.txt"),
            "允许读取的资料",
          );
          assert.equal(await listWorkspace(workspace), "notes.txt");
        },
      );
      await t.test(
        "rejects relative traversal and outside absolute paths",
        async () => {
          await assert.rejects(
            readWorkspace(workspace, "../outside/private.txt"),
            /独立工作区/,
          );
          await assert.rejects(
            readWorkspace(workspace, path.join(outside, "private.txt")),
            /独立工作区/,
          );
        },
      );
      await t.test("rejects junction or symlink escapes", async () => {
        await symlink(
          outside,
          path.join(workspace, "escape"),
          process.platform === "win32" ? "junction" : "dir",
        );
        await assert.rejects(
          readWorkspace(workspace, "escape/private.txt"),
          /独立工作区/,
        );
      });
      await t.test(
        "rejects hidden files, binary formats and oversized text",
        async () => {
          await writeFile(
            path.join(workspace, ".secret.txt"),
            "test-only hidden data",
          );
          await writeFile(
            path.join(workspace, "image.png"),
            "not a text document",
          );
          await writeFile(path.join(workspace, "huge.txt"), "x".repeat(24577));
          await assert.rejects(readWorkspace(workspace, ".secret.txt"), /隐藏/);
          await assert.rejects(readWorkspace(workspace, "image.png"), /仅支持/);
          await assert.rejects(readWorkspace(workspace, "huge.txt"), /24 KiB/);
        },
      );
    } finally {
      const resolved = path.resolve(temporary);
      assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()));
      assert.ok(path.basename(resolved).startsWith("dicebot-harness-tools-"));
      await rm(resolved, { recursive: true, force: true });
    }
  },
);
