import { spawn } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { basename, extname, relative, resolve } from "node:path";
import { randomUUID } from "node:crypto";

const ROOT = resolve(process.env.AUDIOBOOK_WEB_DATA ?? ".toni-web");
const JOBS = resolve(ROOT, "jobs");
const LIBRARY = resolve(process.env.AUDIOBOOK_LIBRARY ?? resolve(ROOT, "library"));
const configuredUploadMb = Number(process.env.WEB_MAX_UPLOAD_MB ?? 100);
const MAX_UPLOAD = (Number.isFinite(configuredUploadMb) && configuredUploadMb >= 1 && configuredUploadMb <= 500 ? configuredUploadMb : 100) * 1024 * 1024;
const MODELS = [
  { id: "omni", name: "OmniVoice", languages: "600+ languages", voice: "Voice design or uploaded voice sample" },
  { id: "pocket", name: "Pocket TTS", languages: "English", voice: "Built-in Alba voice or uploaded voice sample" },
  { id: "kani", name: "Kani TTS", languages: "English", voice: "Built-in voice or uploaded voice sample" },
  { id: "espeech", name: "ESpeech", languages: "Russian", voice: "Uploaded voice sample required" },
  { id: "qwen", name: "Qwen3-TTS", languages: "Multilingual", voice: "Uploaded voice sample required" },
] as const;
const POCKET_SAMPLE = "https://huggingface.co/kyutai/tts-voices/resolve/main/alba-mackenna/casual.wav";

type Job = {
  id: string;
  title: string;
  state: "queued" | "running" | "succeeded" | "failed";
  createdAt: string;
  model: string;
  voice: string;
  voiceInstruction?: string;
  format: string;
  host: string;
  outputDir: string;
  outputName: string;
  error?: string;
  exitCode?: number;
  pid?: number;
};

function ensureDirs() {
  mkdirSync(ROOT, { recursive: true, mode: 0o700 });
  mkdirSync(JOBS, { recursive: true, mode: 0o700 });
  mkdirSync(LIBRARY, { recursive: true, mode: 0o700 });
}

function jobPath(id: string) {
  if (!/^[0-9a-f-]{36}$/.test(id)) throw new Error("Invalid job id");
  return resolve(JOBS, `${id}.json`);
}

function persist(job: Job) {
  const path = jobPath(job.id);
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, JSON.stringify(job, null, 2), { mode: 0o600 });
  renameSync(temporary, path);
}

function loadJob(id: string): Job | null {
  ensureDirs();
  try { return JSON.parse(readFileSync(jobPath(id), "utf8")) as Job; }
  catch { return null; }
}

function hosts(): Record<string, { ssh?: string }> {
  const path = resolve(process.env.TONI_HOSTS_FILE ?? "hosts.local.json");
  try { return JSON.parse(readFileSync(path, "utf8")) as Record<string, { ssh?: string }>; }
  catch { return {}; }
}

function readLog(id: string): string {
  try {
    return readFileSync(resolve(JOBS, id, "render.log"), "utf8")
      .replaceAll(resolve("."), ".")
      .replaceAll(ROOT, "[job-data]")
      .replaceAll(LIBRARY, "[library]")
      .slice(-8000);
  } catch { return ""; }
}

function outputPath(job: Job): string {
  try {
    const runs = readdirSync(job.outputDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort()
      .reverse();
    for (const run of runs) {
      const candidate = resolve(job.outputDir, run, `${job.outputName}.${job.format}`);
      if (existsSync(candidate)) return candidate;
    }
  } catch { /* No output folder yet. */ }
  return resolve(job.outputDir, "missing-output");
}

function status(job: Job) {
  return {
    id: job.id, title: job.title, state: job.state, createdAt: job.createdAt,
    model: job.model, voice: job.voice, format: job.format, host: job.host,
    error: job.error,
    log: job.state === "running" || job.state === "failed" ? readLog(job.id) : "",
    downloadable: job.state === "succeeded",
  };
}

export function isWithinRoot(root: string, target: string) {
  const relativePath = relative(root, target);
  return relativePath !== "" && relativePath !== ".." && !relativePath.startsWith(`..${process.platform === "win32" ? "\\\\" : "/"}`);
}

export function safeTitle(filename: string) {
  const stem = basename(filename, extname(filename)).normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 70);
  return stem || "audiobook";
}

export function validateVoiceInstruction(model: string, instruction: string) {
  if (instruction.length > 300) throw new Error("Voice description must be 300 characters or fewer.");
  if (instruction && model !== "omni") throw new Error("Voice descriptions are supported only by OmniVoice.");
}

export function validateOptions(options: { model: string; format: string; host: string; workers: number; language: string; hasVoice: boolean }, allowedHosts: string[]) {
  if (!MODELS.some((item) => item.id === options.model)) throw new Error("Select a supported model.");
  if (options.format !== "m4b" && options.format !== "mp3") throw new Error("Choose M4B or MP3 output.");
  if (!allowedHosts.includes(options.host)) throw new Error("Select a configured remote render host.");
  if (!Number.isInteger(options.workers) || options.workers < 1 || options.workers > 4) throw new Error("Workers must be between 1 and 4.");
  if (!/^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})?$/.test(options.language)) throw new Error("Enter a valid language code, such as en or ru.");
  if (["qwen", "espeech"].includes(options.model) && !options.hasVoice) throw new Error(`${options.model} requires an uploaded voice sample.`);
}

function run(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv; stdout?: number; stderr?: number } = {}) {
  return new Promise<{ code: number; stderr: string }>((resolvePromise, reject) => {
    let errorText = "";
    const child = spawn(command, args, { cwd: options.cwd, env: options.env, stdio: ["ignore", options.stdout ?? "ignore", options.stderr ?? "pipe"] });
    child.stderr?.on("data", (chunk: Buffer) => { errorText += chunk.toString(); });
    child.once("error", reject);
    child.once("close", (code) => resolvePromise({ code: code ?? 1, stderr: errorText }));
  });
}

export function getMaxRequestBytes() {
  return MAX_UPLOAD + 100 * 1024 * 1024 + 1024 * 1024;
}

export function getConfig() {
  const available = hosts();
  const hostNames = Object.keys(available).filter((name) => available[name]?.ssh);
  return {
    models: MODELS,
    hosts: hostNames,
    defaultHost: process.env.WEB_DEFAULT_HOST && hostNames.includes(process.env.WEB_DEFAULT_HOST)
      ? process.env.WEB_DEFAULT_HOST : hostNames[0] ?? "",
    maxUploadMb: Math.floor(MAX_UPLOAD / (1024 * 1024)),
    samplePreview: POCKET_SAMPLE,
  };
}

export function listJobs() {
  ensureDirs();
  const jobs = readdirSync(JOBS).filter((name) => name.endsWith(".json")).map((name) => {
    try {
      const job = JSON.parse(readFileSync(resolve(JOBS, name), "utf8")) as Job;
      if (job.state === "running" || job.state === "queued") {
        let alive = false;
        if (job.pid) {
          try { process.kill(job.pid, 0); alive = true; } catch { alive = false; }
        }
        if (!alive) {
          job.state = existsSync(outputPath(job)) ? "succeeded" : "failed";
          if (job.state === "failed") job.error = "The render process stopped before completing.";
          persist(job);
        }
      }
      return status(job);
    } catch { return null; }
  }).filter((job): job is NonNullable<typeof job> => job !== null);
  return jobs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function getJob(id: string) {
  const job = loadJob(id);
  return job ? status(job) : null;
}

let submissionInProgress = false;

export async function createJob(form: FormData) {
  ensureDirs();
  if (submissionInProgress || listJobs().some((job) => job.state === "running" || job.state === "queued")) {
    throw new Error("A render is already in progress. Wait for it to finish before starting another.");
  }
  submissionInProgress = true;
  try { return await createJobInternal(form); }
  finally { submissionInProgress = false; }
}

async function createJobInternal(form: FormData) {
  const file = form.get("book");
  const voiceFile = form.get("voice");
  if (!(file instanceof File) || file.size === 0) throw new Error("Choose a TXT or PDF book file.");
  if (file.size > MAX_UPLOAD) throw new Error(`Book exceeds the upload limit (${Math.floor(MAX_UPLOAD / (1024 * 1024))} MB).`);
  const extension = extname(file.name).toLowerCase();
  if (![".txt", ".pdf"].includes(extension)) throw new Error("Only .txt and .pdf book files are supported.");
  const model = String(form.get("model") ?? "pocket");
  const format = String(form.get("format") ?? "m4b");
  const host = String(form.get("host") ?? "");
  const availableHosts = hosts();
  const workers = Number(form.get("workers") ?? 1);
  const language = String(form.get("language") ?? "en").trim();
  const voiceInstruction = String(form.get("voiceInstruction") ?? "").trim();
  validateVoiceInstruction(model, voiceInstruction);
  if (voiceFile && (!(voiceFile instanceof File) || voiceFile.size > 100 * 1024 * 1024)) throw new Error("Voice sample must be an audio file smaller than 100 MB.");
  if (voiceFile instanceof File && voiceFile.size > 0 && ![".wav", ".mp3", ".m4a", ".flac", ".ogg"].includes(extname(voiceFile.name).toLowerCase())) {
    throw new Error("Voice samples must be WAV, MP3, M4A, FLAC, or OGG audio.");
  }
  validateOptions({ model, format, host, workers, language, hasVoice: voiceFile instanceof File && voiceFile.size > 0 },
    Object.keys(availableHosts).filter((name) => availableHosts[name]?.ssh));

  const id = randomUUID();
  const title = safeTitle(file.name);
  const outputName = `${title}-${id.slice(0, 8)}`;
  const storageDir = resolve(JOBS, id);
  const outputDir = resolve(LIBRARY, outputName);
  mkdirSync(storageDir, { recursive: true, mode: 0o700 });
  mkdirSync(outputDir, { recursive: true, mode: 0o700 });
  let text: string;
  try {
    if (extension === ".txt") {
      try { text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
      catch { throw new Error("The text file is not valid UTF-8. Convert it to UTF-8 and try again."); }
      if (!text.trim()) throw new Error("The text file is empty.");
      writeFileSync(resolve(storageDir, "source.txt"), text, { mode: 0o600 });
    } else {
      const pdfPath = resolve(storageDir, "upload.pdf");
      const textPath = resolve(storageDir, "source.txt");
      writeFileSync(pdfPath, Buffer.from(await file.arrayBuffer()), { mode: 0o600 });
      const extracted = await run("pdftotext", ["-layout", "-enc", "UTF-8", pdfPath, textPath]);
      if (extracted.code !== 0) throw new Error("Could not extract this PDF. Make sure it is a valid, text-based PDF; scanned books need OCR first.");
      text = readFileSync(textPath, "utf8");
      if (!text.trim()) throw new Error("No selectable text was found. This PDF may be scanned; run OCR before uploading.");
    }
    if (voiceFile instanceof File && voiceFile.size > 0) {
      const voiceExt = extname(voiceFile.name).toLowerCase();
      writeFileSync(resolve(storageDir, `voice${voiceExt}`), Buffer.from(await voiceFile.arrayBuffer()), { mode: 0o600 });
    }
  } catch (error) {
    rmSync(storageDir, { recursive: true, force: true });
    rmSync(outputDir, { recursive: true, force: true });
    throw error;
  }
  const job: Job = {
    id, title: file.name, state: "running", createdAt: new Date().toISOString(), model,
    voice: voiceFile instanceof File && voiceFile.size > 0 ? voiceFile.name : "Model default",
    format, host, outputDir, outputName,
    ...(voiceInstruction ? { voiceInstruction } : {}),
  };
  persist(job);
  const logPath = resolve(storageDir, "render.log");
  const fd = openSync(logPath, "a", 0o600);
  const runner = resolve(process.env.TONI_RECORD_SCRIPT ?? "scripts/record_audiobook.sh");
  const args = ["--input", resolve(storageDir, "source.txt"), "--name", outputName,
    "--output-dir", LIBRARY, "--model", model, "--host", host, "--format", format,
    "--workers", String(workers), "--language", language];
  if (voiceInstruction) args.push("--voice-instruction", voiceInstruction);
  const voicePath = readdirSync(storageDir).find((name) => name.startsWith("voice."));
  if (voicePath) args.push("--voice", resolve(storageDir, voicePath));
  const child = spawn(runner, args, {
    cwd: resolve("."), env: { ...process.env, AUDIOBOOK_LIBRARY: LIBRARY, TONI_LANGUAGE: language },
    detached: true, stdio: ["ignore", fd, fd],
  });
  closeSync(fd);
  child.unref();
  if (child.pid) { job.pid = child.pid; persist(job); }
  child.once("error", (error) => {
    job.state = "failed"; job.error = "Could not start the render process. Check the server configuration."; persist(job);
  });
  child.once("close", (code) => {
    job.exitCode = code ?? 1;
    job.state = code === 0 ? "succeeded" : "failed";
    if (code !== 0) job.error = `Render exited with status ${code ?? "unknown"}. Check the log for details.`;
    persist(job);
  });
  return { ...status(job), preview: text.slice(0, 600) };
}

export function getDownload(id: string) {
  const job = loadJob(id);
  if (!job || job.state !== "succeeded") return null;
  const path = outputPath(job);
  if (!isWithinRoot(LIBRARY, path) || !existsSync(path)) return null;
  return { path, filename: `${safeTitle(job.title)}.${job.format}` };
}
