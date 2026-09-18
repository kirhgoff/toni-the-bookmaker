export interface RunResult {
  stdout: string;
  stderr: string;
  code: number;
}

export async function run(
  cmd: string[],
  opts: { stdin?: string; inherit?: boolean; cwd?: string } = {},
): Promise<RunResult> {
  const proc = Bun.spawn(cmd, {
    cwd: opts.cwd,
    stdin: opts.stdin === undefined ? "ignore" : new TextEncoder().encode(opts.stdin),
    stdout: opts.inherit ? "inherit" : "pipe",
    stderr: opts.inherit ? "inherit" : "pipe",
  });

  const [stdout, stderr] = await Promise.all([
    opts.inherit ? Promise.resolve("") : new Response(proc.stdout).text(),
    opts.inherit ? Promise.resolve("") : new Response(proc.stderr).text(),
  ]);
  const code = await proc.exited;
  return { stdout, stderr, code };
}

export async function runOrThrow(
  cmd: string[],
  opts: { stdin?: string; inherit?: boolean; cwd?: string } = {},
): Promise<RunResult> {
  const result = await run(cmd, opts);
  if (result.code !== 0) {
    const detail = result.stderr.trim() || result.stdout.trim();
    throw new Error(`${cmd[0]} exited ${result.code}${detail ? `: ${detail}` : ""}`);
  }
  return result;
}

export async function requireCommand(name: string, hint: string): Promise<void> {
  const { code } = await run(["sh", "-c", `command -v ${name}`]);
  if (code !== 0) throw new Error(`${name} is not installed. ${hint}`);
}

/** Single-quote a string for safe interpolation into a remote bash script. */
export function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`;
}

export function log(message: string): void {
  const now = new Date().toTimeString().slice(0, 8);
  console.log(`[${now}] ${message}`);
}
