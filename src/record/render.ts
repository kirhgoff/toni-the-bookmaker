import { basename } from "node:path";

import { gpuArgsOf, resolveHost, runtimeOf } from "./hosts.ts";
import { log, runOrThrow, shellQuote } from "./shell.ts";

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
  chapterPattern?: string;
  voiceRef?: string;
  refText?: string;
}

function cliArgs(o: RenderOptions, inDir: string, outDir: string): string[] {
  const args = [
    "-i", `${inDir}/source.txt`,
    "-o", `${outDir}/${o.name}.${o.format}`,
    "-m", o.model,
    "--bitrate", o.bitrate,
    "--chunk-pause", String(o.pauseMs),
    "--workers", String(o.workers),
    "--work-dir", `${outDir}/work`,
  ];
  if (o.voiceRef) args.push("-v", `${inDir}/voice_ref.wav`);
  if (o.chapterPattern) args.push("--chapter-pattern", o.chapterPattern);
  return args;
}

export async function renderLocal(o: RenderOptions): Promise<void> {
  log(`Rendering locally with ${o.workers} workers (re-run to resume)`);
  const env: Record<string, string> = {
    ...process.env as Record<string, string>,
    TONI_LANGUAGE: o.language,
  };
  if (o.refText) env.TONI_REF_TEXT = o.refText;

  const proc = Bun.spawn(
    ["uv", "run", "--project", o.projectDir, "--extra", o.model,
     "python", "-m", "toni.cli", ...cliArgs(o, o.bookDir, o.runDir)],
    { env, stdout: "inherit", stderr: "inherit" },
  );
  const code = await proc.exited;
  if (code !== 0) throw new Error(`render failed (exit ${code})`);
}

export async function renderRemote(hostName: string, o: RenderOptions): Promise<void> {
  const host = resolveHost(hostName);
  const key = `${process.env.HOME}/${host.identity}`;
  const sshCmd = `ssh -i ${key} -o ConnectTimeout=10`;
  const ssh = ["ssh", "-i", key, "-o", "ConnectTimeout=10", host.ssh];
  const image = host.image ?? `toni:${o.model}`;
  const runtime = runtimeOf(host);
  const gpuArgs = gpuArgsOf(host).join(" ");

  const remoteSh = async (script: string) => {
    const proc = Bun.spawn([...ssh, host.shell], {
      stdin: new TextEncoder().encode(`${script}\n`),
      stdout: "pipe",
      stderr: "pipe",
    });
    const out = await new Response(proc.stdout).text();
    return { out: out.trim(), code: await proc.exited };
  };

  const { out: remoteHome, code: homeCode } = await remoteSh("printf %s \"$HOME\"");
  if (homeCode !== 0 || !remoteHome.startsWith("/")) {
    throw new Error(`could not resolve remote home on ${hostName} (got "${remoteHome}")`);
  }
  const jobDir = `${remoteHome}/${host.workdir}/${o.name}/${basename(o.runDir)}`;

  const rsync = (from: string, to: string) => {
    const cmd = ["rsync", "-a", "--partial", "--inplace", "-e", sshCmd];
    if (host.rsyncPath) cmd.push(`--rsync-path=${host.rsyncPath}`);
    return runOrThrow([...cmd, from, to], { inherit: true });
  };

  log(`Rendering on ${hostName} with ${o.workers} workers`);

  log("  uploading inputs");
  await remoteSh(`mkdir -p ${shellQuote(jobDir)}`);
  await rsync(`${o.bookDir}/source.txt`, `${host.ssh}:${jobDir}/source.txt`);
  if (o.voiceRef) await rsync(o.voiceRef, `${host.ssh}:${jobDir}/voice_ref.wav`);

  const envExports = Object.entries(host.env ?? {})
    .map(([k, v]) => `export ${k}=${v}`).join("\n");
  const dockerEnv = [
    "-e", `TONI_LANGUAGE=${shellQuote(o.language)}`,
    ...(o.refText ? ["-e", `TONI_REF_TEXT=${shellQuote(o.refText)}`] : []),
  ].join(" ");

  const script = [
    "set -e",
    envExports,
    `WORKDIR=${shellQuote(jobDir)}`,
    "exec 9>/tmp/toni-gpu.lock",
    'flock -n 9 || { echo "GPU is busy: another render holds the lease" >&2; exit 75; }',
    host.leaseAcquire ?? "",
    // A container outlives the ssh session that started it, so name it: kill
    // any leftover from an interrupted run, and take it down on exit.
    `CONTAINER=toni-${o.name}`,
    `${runtime} rm -f "$CONTAINER" >/dev/null 2>&1 || true`,
    `trap '${runtime} rm -f "$CONTAINER" >/dev/null 2>&1' EXIT INT TERM HUP`,
    `${runtime} run --rm --name "$CONTAINER" ${gpuArgs} -v "$WORKDIR:/books" ` +
      `-v toni-models:/models ${dockerEnv} ` +
      `${image} ${cliArgs(o, "/books", "/books").map(shellQuote).join(" ")}`,
  ].filter(Boolean).join("\n");

  // Ship the script as a file rather than on stdin: commands inside it
  // (docker, ollama) read stdin themselves and would swallow the remainder.
  const scriptPath = `${o.runDir}/.render.sh`;
  await Bun.write(scriptPath, `${script}\n`);
  await rsync(scriptPath, `${host.ssh}:${jobDir}/run.sh`);

  const proc = Bun.spawn([...ssh, host.shell], {
    stdin: new TextEncoder().encode(`bash ${shellQuote(`${jobDir}/run.sh`)} < /dev/null\n`),
    stdout: "inherit",
    stderr: "inherit",
  });
  const code = await proc.exited;
  if (code === 75) throw new Error(`${hostName} GPU is busy (another render holds the lease)`);
  if (code !== 0) throw new Error(`remote render failed (exit ${code})`);

  log("  downloading result");
  await rsync(`${host.ssh}:${jobDir}/${o.name}.${o.format}`, `${o.runDir}/${o.name}.${o.format}`);
}
