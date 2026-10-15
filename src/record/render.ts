import { copyFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { basename, join } from "node:path";

import { resolveHost, type RenderHost } from "./hosts.ts";
import { log, runOrThrow } from "./shell.ts";

const BUSY_EXIT = 75;
const MAX_MESSAGE_CHARS = 500;
const STDERR_TAIL_CHARS = 4096;

export interface RenderOptions {
  projectDir: string;
  bookDir: string;
  runDir: string;
  name: string;
  format: string;
  bitrate: string;
  pauseMs: number;
  workers: number;
  language: string;
  model: string;
  seed?: string;
  batch?: string;
  qc: boolean;
  chapterPattern?: string;
  voiceInstruction?: string;
  voiceRef?: string;
  lexicon?: string;
  refText?: string;
  coverFile?: string;
  chapterTitlesFile?: string;
}

export function cliArgs(
  o: RenderOptions,
  inDir: string,
  outDir: string,
  cacheDir = `${inDir}/cache`,
): string[] {
  const args = [
    "-i", `${inDir}/source.txt`,
    "-o", `${outDir}/${o.name}.${o.format}`,
    "-m", o.model,
    "--bitrate", o.bitrate,
    "--chunk-pause", String(o.pauseMs),
    "--workers", String(o.workers),
    "--work-dir", `${outDir}/work`,
    "--cache-dir", cacheDir,
  ];
  if (o.voiceRef) args.push("-v", `${inDir}/voice_ref.wav`);
  if (o.coverFile) args.push("--cover", `${inDir}/${o.coverFile}`);
  if (o.chapterTitlesFile) args.push("--chapter-titles", `${inDir}/${o.chapterTitlesFile}`);
  if (o.lexicon) args.push("--lexicon", `${inDir}/lexicon.txt`);
  if (o.seed) args.push("--seed", o.seed);
  if (o.batch) args.push("--batch", o.batch);
  if (!o.qc) args.push("--no-qc");
  if (o.chapterPattern) args.push("--chapter-pattern", o.chapterPattern);
  return args;
}

export function dockerEnvFlags(o: RenderOptions, env: Record<string, string | undefined> = process.env): string[] {
  return [
    "-e", `TONI_LANGUAGE=${o.language}`,
    ...(o.refText ? ["-e", `TONI_REF_TEXT=${o.refText}`] : []),
    ...(o.voiceInstruction ? ["-e", `TONI_OMNI_INSTRUCT=${o.voiceInstruction}`] : []),
    ...(env.TONI_NORMALIZE ? ["-e", `TONI_NORMALIZE=${env.TONI_NORMALIZE}`] : []),
    ...Object.entries(env)
      .filter(([k, v]) => (k.startsWith("TONI_QC") || k === "TONI_BATCH" || k === "TONI_OMNI_COMPILE") && v !== undefined)
      .flatMap(([k, v]) => ["-e", `${k}=${v!}`]),
  ];
}

export async function renderLocal(o: RenderOptions): Promise<void> {
  log(`Rendering locally with ${o.workers} workers (re-run to resume)`);
  const env: Record<string, string> = {
    ...process.env as Record<string, string>,
    TONI_LANGUAGE: o.language,
  };
  if (o.refText) env.TONI_REF_TEXT = o.refText;
  if (o.voiceInstruction) env.TONI_OMNI_INSTRUCT = o.voiceInstruction;

  const proc = Bun.spawn(
    ["uv", "run", "--project", o.projectDir, "--extra", o.model,
     "python", "-m", "toni.cli", ...cliArgs(o, o.bookDir, o.runDir)],
    { env, stdout: "inherit", stderr: "inherit" },
  );
  const code = await proc.exited;
  if (code !== 0) throw new Error(`render failed (exit ${code})`);
}

const slug = (value: string) => value.replace(/[^\w.-]+/g, "-").replace(/\.{2,}/g, ".");

export interface RemoteJob {
  slug: string;
  holder: string;
  container: string;
  rel: string;
  cacheRel: string;
  image: string;
  output: string;
}

export function remoteJob(o: RenderOptions, host: RenderHost, shortHost: string): RemoteJob {
  const name = slug(o.name);
  const book = `toni/${name}`;
  const rel = `${book}/${slug(basename(o.runDir))}`;
  return {
    slug: name,
    holder: `toni@${shortHost}`,
    container: `toni-${name}`,
    rel,
    cacheRel: `${book}/cache`,
    image: host.image ?? `toni:${o.model}`,
    output: `${rel}/${name}.${o.format}`,
  };
}

export function podmanRunArgv(o: RenderOptions, job: RemoteJob, env = process.env): string[] {
  return [
    "localbrains", "podman", "--as", job.holder, "run",
    "--name", job.container,
    "-v", `./${job.rel}:/books`,
    "-v", `./${job.cacheRel}:/cache`,
    "-v", "toni-models:/models",
    ...dockerEnvFlags(o, env),
    job.image,
    ...cliArgs({ ...o, name: job.slug }, "/books", "/books", "/cache"),
  ];
}

export function putArgv(stageDir: string): string[] {
  return ["localbrains", "put", `${stageDir}/`, "toni/"];
}

export function getArgv(job: RemoteJob, localOutput: string): string[] {
  return ["localbrains", "get", job.output, localOutput];
}

function lastLine(text: string): string {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  return (lines.at(-1) ?? "").slice(0, MAX_MESSAGE_CHARS);
}

export function renderFailure(hostName: string, code: number, stderr: string): Error | undefined {
  if (code === 0) return undefined;
  if (code === BUSY_EXIT) return new Error(`${hostName} GPU is busy or the lease was revoked: ${lastLine(stderr)}`);
  return new Error(`remote render failed (exit ${code})`);
}

async function teeStderr(stream: ReadableStream<Uint8Array>): Promise<string> {
  const decoder = new TextDecoder();
  let text = "";
  for await (const chunk of stream) {
    process.stderr.write(chunk);
    text = (text + decoder.decode(chunk, { stream: true })).slice(-STDERR_TAIL_CHARS);
  }
  return text;
}

async function stageInputs(o: RenderOptions, job: RemoteJob): Promise<string> {
  const stage = await mkdtemp(join(tmpdir(), "toni-stage-"));
  const runDir = join(stage, job.slug, basename(job.rel));
  await mkdir(runDir, { recursive: true });
  await mkdir(join(stage, job.slug, "cache"), { recursive: true });
  const inputs: [string, string][] = [[`${o.bookDir}/source.txt`, "source.txt"]];
  if (o.voiceRef) inputs.push([o.voiceRef, "voice_ref.wav"]);
  if (o.lexicon) inputs.push([o.lexicon, "lexicon.txt"]);
  if (o.coverFile) inputs.push([`${o.bookDir}/${o.coverFile}`, o.coverFile]);
  if (o.chapterTitlesFile) inputs.push([`${o.bookDir}/${o.chapterTitlesFile}`, o.chapterTitlesFile]);
  for (const [from, to] of inputs) await copyFile(from, join(runDir, to));
  return stage;
}

export async function renderRemote(hostName: string, o: RenderOptions): Promise<void> {
  const host = resolveHost(hostName);
  const job = remoteJob(o, host, hostname().split(".")[0]!);

  log(`Rendering on ${hostName} with ${o.workers} workers`);

  log("  uploading inputs");
  const stage = await stageInputs(o, job);
  try {
    await runOrThrow(putArgv(stage), { inherit: true });
  } finally {
    await rm(stage, { recursive: true, force: true });
  }

  const proc = Bun.spawn(podmanRunArgv(o, job), { stdout: "inherit", stderr: "pipe" });
  const [stderr, code] = await Promise.all([teeStderr(proc.stderr), proc.exited]);
  const failure = renderFailure(hostName, code, stderr);
  if (failure) throw failure;

  log("  downloading result");
  await runOrThrow(getArgv(job, `${o.runDir}/${o.name}.${o.format}`), { inherit: true });
}
