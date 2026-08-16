// Types for the Nutanix management API.
// The API fronts the MCP tool surface: one generic execute endpoint plus auth.
// Kept intentionally small — tool `data` payloads are cluster-shaped and vary,
// so they're typed as `unknown` and rendered defensively in the UI.

export type Role = "viewer" | "operator" | "admin";

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  username: string;
  role: Role;
}

export interface Identity {
  username: string;
  role: Role;
}

export interface ApiConfig {
  default_pe_host: string;
  allowed_pe_hosts: string[];
  pe_only: boolean;
  roles: Record<Role, number>;
  your_role: Role;
}

// JSON Schema (subset) as advertised by the catalogue, enough to render forms.
export interface JsonSchemaProperty {
  type?: "string" | "integer" | "number" | "boolean" | "array" | "object";
  description?: string;
  default?: unknown;
  enum?: unknown[];
}

export interface ToolInputSchema {
  type: "object";
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

export interface ToolInfo {
  name: string;
  title?: string;
  description?: string;
  inputSchema?: ToolInputSchema;
  min_role: Role;
  destructive: boolean;
  /** Whether the *current* user may run this tool (from GET /api/tools). */
  allowed: boolean;
}

export interface ToolResult<T = unknown> {
  tool: string;
  data: T;
}

/** Error body shape returned by the API for every non-2xx response. */
export interface ApiErrorBody {
  detail: string;
}
