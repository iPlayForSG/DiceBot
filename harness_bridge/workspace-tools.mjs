import path from "node:path";
import { pathToFileURL } from "node:url";
import { realpath, readdir, readFile, stat } from "node:fs/promises";

const moduleRoot = process.env.DICEBOT_HARNESS_PACKAGE_ROOT;
const { defineTool } = await import(
  pathToFileURL(
    path.join(moduleRoot, "node_modules/@deepseek-ai/dsh-tools/lib/index.js"),
  ).href
);
export const name = "dicebot-workspace-tools";
export const inject = ["tools"];
const textExtensions = new Set([".txt", ".md", ".json", ".csv", ".tsv"]);

export async function confinedPath(root, requested) {
  if (
    typeof requested !== "string" ||
    requested.length > 300 ||
    requested.includes("\0")
  )
    throw new Error("路径不合法");
  const physicalRoot = await realpath(root);
  const candidate = path.resolve(physicalRoot, requested);
  const lexical = path.relative(physicalRoot, candidate);
  if (
    path.isAbsolute(lexical) ||
    lexical === ".." ||
    lexical.startsWith(".." + path.sep)
  )
    throw new Error("只能读取当前会话的独立工作区");
  const physical = await realpath(candidate);
  const relative = path.relative(physicalRoot, physical);
  // 文件系统边界由工具所有者检查，不能依赖模型遵守提示词或逻辑 cwd。
  if (
    path.isAbsolute(relative) ||
    relative === ".." ||
    relative.startsWith(".." + path.sep)
  )
    throw new Error("只能读取当前会话的独立工作区");
  if (relative.split(path.sep).some((part) => part.startsWith(".")))
    throw new Error("不提供隐藏文件");
  return physical;
}

export async function listWorkspace(root, requested = ".") {
  const target = await confinedPath(root, requested);
  const entries = await readdir(target, { withFileTypes: true });
  return entries
    .filter((entry) => !entry.name.startsWith(".") && !entry.isSymbolicLink())
    .slice(0, 100)
    .map((entry) => entry.name + (entry.isDirectory() ? "/" : ""))
    .join("\n");
}

export async function readWorkspace(root, requested, signal) {
  const target = await confinedPath(root, requested);
  if (!textExtensions.has(path.extname(target).toLowerCase()))
    throw new Error("仅支持 txt、md、json、csv、tsv 文本资料");
  const info = await stat(target);
  if (!info.isFile() || info.size > 24576)
    throw new Error("文件必须是小于 24 KiB 的文本文件");
  return readFile(target, { encoding: "utf8", signal });
}

export function apply(ctx) {
  const root = process.env.DICEBOT_HARNESS_WORKSPACE;
  ctx.tools.register(
    defineTool({
      name: "list_workspace",
      description: "列出当前 QQ 会话独立工作区的资料，路径相对于工作区。",
      parameters: { path: { type: "string", description: "相对目录，默认 ." } },
      output: {
        schema: { type: "string" },
        render: (_args, value) => [{ type: "text", text: value }],
      },
      async execute(args) {
        return listWorkspace(root, args.path ?? ".");
      },
    }),
  );
  ctx.tools.register(
    defineTool({
      name: "read_workspace",
      description:
        "读取当前 QQ 会话独立工作区的文本资料，不可读取工作区之外的文件。",
      parameters: {
        path: {
          type: "string",
          required: true,
          description: "相对文本文件路径",
        },
      },
      output: {
        schema: { type: "string" },
        render: (_args, value) => [{ type: "text", text: value }],
      },
      async execute(args, execution) {
        return readWorkspace(root, args.path, execution.signal);
      },
    }),
  );
}
