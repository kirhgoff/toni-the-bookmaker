import { resolve } from "node:path";

export interface RenderHost {
  /** Image to run instead of `toni:<model>`. */
  image?: string;
}

export const HOSTS_FILE = resolve(import.meta.dir, "../../hosts.local.json");

export const HOSTS: Record<string, RenderHost> = await Bun.file(HOSTS_FILE)
  .json()
  .catch(() => ({}));

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
