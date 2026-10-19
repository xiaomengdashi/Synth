import { adminFetch } from '../../utils/adminAuth.ts';
import type { ConversationSummary, ConversationDetail, KnowledgeStatus, KnowledgeTurn } from './types';

export class KnowledgeRequestError extends Error {
  status: number;
  constructor(message: string, status: number) { super(message); this.status = status; }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await adminFetch(`/api/v1/knowledge${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...init.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new KnowledgeRequestError(typeof data?.detail === 'string' ? data.detail : '请求未完成，请稍后重试。', response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const knowledgeClient = {
  status: () => request<KnowledgeStatus>('/status'),
  list: (limit = 30, offset = 0) => request<{total: number; data: ConversationSummary[]}>(`/conversations?limit=${limit}&offset=${offset}`),
  create: () => request<ConversationSummary>('/conversations', {method:'POST'}),
  get: (id: string) => request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`),
  remove: (id: string) => request<void>(`/conversations/${encodeURIComponent(id)}`, {method:'DELETE'}),
  send: (id: string, question: string, requestId: string) => request<KnowledgeTurn>(`/conversations/${encodeURIComponent(id)}/messages`, {
    method:'POST', body:JSON.stringify({question, request_id:requestId}),
  }),
};
