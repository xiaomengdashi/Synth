import type { ParameterSchema, QueryParameter } from './types';

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`服务返回了无法读取的响应（HTTP ${response.status}），请稍后重试。`); }
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map(item => item.msg || '参数无效').join('；') : `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return data as T;
}

export function fieldSchema(schema: ParameterSchema): ParameterSchema {
  return schema.anyOf?.find(item => item.type !== 'null') || schema;
}

export function schemaType(schema: ParameterSchema): string {
  return fieldSchema(schema).type || 'string';
}

function assertSafeNumbers(value: unknown) {
  if (typeof value === 'number' && (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))) {
    throw new Error('JSON 中的长整数会丢失精度，请将 ID 写成带引号的字符串。');
  }
  if (Array.isArray(value)) value.forEach(assertSafeNumbers);
  else if (value && typeof value === 'object') Object.values(value).forEach(assertSafeNumbers);
}

export function buildParameters(fields: QueryParameter[], values: Record<string, string>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = (values[field.name] ?? '').trim();
    if (!value) {
      if (field.required) throw new Error(`请填写 ${field.name}。`);
      continue;
    }
    const type = schemaType(field.schema);
    if (type === 'integer' || type === 'number') {
      const numeric = Number(value);
      if (!Number.isFinite(numeric) || (type === 'integer' && !Number.isSafeInteger(numeric))) {
        throw new Error(`${field.name} 需要有效${type === 'integer' ? '安全整数' : '数字'}。`);
      }
      result[field.name] = numeric;
    } else if (type === 'boolean') {
      if (!['true', 'false'].includes(value)) throw new Error(`${field.name} 请选择是或否。`);
      result[field.name] = value === 'true';
    } else if (type === 'object' || type === 'array') {
      let parsed;
      try { parsed = JSON.parse(value); }
      catch { throw new Error(`${field.name} 需要有效的 JSON。`); }
      assertSafeNumbers(parsed);
      result[field.name] = parsed;
    } else result[field.name] = value;
  }
  return result;
}

export const money = (value: number | null | undefined, digits = 3) =>
  typeof value === 'number' && Number.isFinite(value) ? `$${value.toFixed(digits)}` : '—';

export const dateTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
};
