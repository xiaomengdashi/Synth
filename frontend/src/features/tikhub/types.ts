export interface KeyStatus {
  configured: boolean;
  source?: 'config' | 'environment' | null;
  masked_key?: string;
  has_saved_key?: boolean;
}

export interface Account extends KeyStatus {
  api_key?: { name: string; status: number | null; created_at: string | null; expires_at: string | null; scopes: string[]; scopes_count: number };
  user?: { email: string; balance: number | null; free_credit: number | null; is_active: boolean; account_disabled: boolean; email_verified: boolean };
  daily_usage?: { date: string; usage: number | null; total_request_per_day: number | null; paid_request_per_day: number | null; uri_counts: Record<string, number> } | null;
  warnings?: string[];
  updated_at?: string;
}

export interface ParameterSchema {
  type?: string;
  anyOf?: ParameterSchema[];
  enum?: (string | number | boolean)[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
}

export interface QueryParameter {
  name: string;
  required?: boolean;
  schema: ParameterSchema;
  description?: string;
  example?: unknown;
  in?: string;
}

export interface Endpoint {
  id: string;
  platform: string;
  title: string;
  path: string;
  method: string;
  group: string;
  description: string;
  docs_url: string;
  parameters: QueryParameter[];
}

export interface Catalog {
  source: string;
  generated_at: string;
  platforms: { id: string; name: string; count: number }[];
  total: number;
  items: Endpoint[];
  offset: number;
  limit: number;
}

export interface QueryResult {
  endpoint: Pick<Endpoint, 'id' | 'title' | 'method' | 'path'>;
  data: unknown;
  queried_at: string;
}
