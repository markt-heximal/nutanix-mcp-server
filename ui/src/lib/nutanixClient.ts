// Typed client for the Nutanix management API.
//
// The browser only ever holds a short-lived JWT — never Nutanix credentials.
// Every cluster read/write goes through `callTool(name, arguments, confirm?)`,
// which POSTs to /api/tools/{name}. Reads and writes share this one path; the
// server enforces role-based access and destructive-op confirmation.
//
// Usage:
//   const api = new NutanixClient(getBaseUrl());
//   await api.login(username, password);           // stores the token
//   const { data } = await api.callTool("list_vms", { limit: 100 });
//   await api.callTool("delete_vm", { vm_uuid }, true);   // confirm=true

import type {
  ApiConfig,
  ApiErrorBody,
  Identity,
  LoginResponse,
  ToolInfo,
  ToolResult,
} from "./types";

const TOKEN_KEY = "nutanix.jwt";
const BASE_KEY = "nutanix.apiBaseUrl";

/** Resolve the API base URL: runtime override (localStorage) → build-time env. */
export function getBaseUrl(): string {
  const override =
    typeof localStorage !== "undefined" ? localStorage.getItem(BASE_KEY) : null;
  // Vite exposes VITE_* on import.meta.env.
  const env =
    (import.meta as unknown as { env?: Record<string, string> }).env
      ?.VITE_API_BASE_URL ?? "";
  return (override || env || "").replace(/\/+$/, "");
}

export function setBaseUrl(url: string): void {
  localStorage.setItem(BASE_KEY, url.replace(/\/+$/, ""));
}

/** Thrown for any non-2xx response; carries the HTTP status and API `detail`. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export class NutanixClient {
  private token: string | null;

  constructor(private baseUrl: string = getBaseUrl()) {
    this.token =
      typeof localStorage !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
  }

  get isAuthenticated(): boolean {
    return !!this.token;
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
    auth = true,
  ): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    if (auth && this.token) headers.set("Authorization", `Bearer ${this.token}`);

    const res = await fetch(`${this.baseUrl}${path}`, { ...init, headers });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as ApiErrorBody;
        if (body?.detail) detail = body.detail;
      } catch {
        /* non-JSON error body — keep statusText */
      }
      if (res.status === 401) this.logout(); // token invalid/expired
      throw new ApiError(res.status, detail);
    }
    // 204/empty bodies are not expected on this API, but guard anyway.
    const text = await res.text();
    return (text ? JSON.parse(text) : {}) as T;
  }

  // ── Auth ────────────────────────────────────────────────────────────────
  async login(username: string, password: string): Promise<LoginResponse> {
    const data = await this.request<LoginResponse>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
      false,
    );
    this.token = data.access_token;
    localStorage.setItem(TOKEN_KEY, data.access_token);
    return data;
  }

  logout(): void {
    this.token = null;
    if (typeof localStorage !== "undefined") localStorage.removeItem(TOKEN_KEY);
  }

  me(): Promise<Identity> {
    return this.request<Identity>("/api/me", { method: "GET" });
  }

  config(): Promise<ApiConfig> {
    return this.request<ApiConfig>("/api/config", { method: "GET" });
  }

  // ── Tools ───────────────────────────────────────────────────────────────
  async listTools(): Promise<ToolInfo[]> {
    const { tools } = await this.request<{ tools: ToolInfo[] }>("/api/tools", {
      method: "GET",
    });
    return tools;
  }

  /**
   * Execute a tool. `confirm` must be true for tools whose catalogue entry has
   * `destructive === true` (delete_vm, power_off_vm, update_vm, restore_vm_snapshot),
   * otherwise the API returns 428.
   */
  callTool<T = unknown>(
    name: string,
    args: Record<string, unknown> = {},
    confirm = false,
  ): Promise<ToolResult<T>> {
    return this.request<ToolResult<T>>(`/api/tools/${name}`, {
      method: "POST",
      body: JSON.stringify({ arguments: args, confirm }),
    });
  }

  /** Convenience: poll get_task until it stops running or attempts run out. */
  async waitForTask(
    taskUuid: string,
    { intervalMs = 2000, maxAttempts = 60 } = {},
  ): Promise<unknown> {
    for (let i = 0; i < maxAttempts; i++) {
      const { data } = await this.callTool("get_task", { task_uuid: taskUuid });
      const status = String(
        (data as { status?: string; state?: string })?.status ??
          (data as { state?: string })?.state ??
          "",
      ).toUpperCase();
      if (status && !["RUNNING", "QUEUED", "PENDING"].includes(status)) return data;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new ApiError(504, "Timed out waiting for task to complete.");
  }
}
