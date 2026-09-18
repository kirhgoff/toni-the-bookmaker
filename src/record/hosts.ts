import { resolve } from "node:path";

export interface RenderHost {
  /** SSH destination, e.g. "user@gpu-box". */
  ssh: string;
  /** Private key path, relative to $HOME. */
  identity: string;
  /**
   * Command that receives a bash script on stdin and runs it where docker
   * lives. Plain Linux hosts use "bash -s"; a Windows box running Docker
   * Desktop needs the WSL hop.
   */
  shell: string;
  /**
   * How rsync is invoked on the host. SSH may land in a shell that cannot see
   * the docker host's filesystem (Windows -> WSL), so rsync has to be run
   * through the same hop; paths are then native to that side.
   */
  rsyncPath?: string;
  /** Job directory on the docker host, relative to that user's home. */
  workdir: string;
  /** Container runtime on the host: "docker" (default) or "podman". */
  runtime?: string;
  /**
   * Flags that expose the GPU. Docker uses --gpus; podman addresses devices
   * through CDI instead.
   */
  gpuArgs?: string[];
  /** Extra environment exported before the container runs on the host. */
  env?: Record<string, string>;
  /**
   * Command run before the render to free VRAM, e.g. evicting an LLM.
   * Evicting a model is preferred over stopping its daemon: nothing has to be
   * restarted afterwards, so a crashed render cannot leave the box degraded.
   */
  leaseAcquire?: string;
  image?: string;
}

export const HOSTS_FILE = resolve(import.meta.dir, "../../hosts.local.json");

export const HOSTS: Record<string, RenderHost> = await Bun.file(HOSTS_FILE)
  .json()
  .catch(() => ({}));

export function runtimeOf(host: RenderHost): string {
  return host.runtime ?? "docker";
}

export function gpuArgsOf(host: RenderHost): string[] {
  if (host.gpuArgs) return host.gpuArgs;
  return runtimeOf(host) === "podman"
    ? ["--device", "nvidia.com/gpu=all"]
    : ["--gpus", "all"];
}

export function resolveHost(name: string): RenderHost {
  const host = HOSTS[name];
  if (!host) {
    const known = Object.keys(HOSTS).join(", ") || "none";
    throw new Error(
      `Unknown render host "${name}". Known hosts: ${known}. Define hosts in ${HOSTS_FILE} (see hosts.example.json)`,
    );
  }
  return host;
}
