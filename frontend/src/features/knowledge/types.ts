export interface KnowledgeSource {
  number: number; article_id: string; title: string; source_type: string;
  excerpt: string; article_updated_at: string; article_exists: boolean;
}
export interface KnowledgeTurn {
  id: string; conversation_id: string; request_id: string; question: string; answer: string;
  status: 'pending' | 'completed' | 'failed' | 'interrupted';
  insufficient_evidence: boolean; sources: KnowledgeSource[]; error_message: string;
  created_at: string; completed_at: string;
}
export interface ConversationSummary { id: string; title: string; created_at: string; updated_at: string }
export interface ConversationDetail { conversation: ConversationSummary; turns: KnowledgeTurn[] }
export type ConversationCache = Record<string, ConversationDetail & {lastMutationAt: number}>;
export interface KnowledgeStatus {
  model_configured: boolean; index_available: boolean; article_count: number;
  indexed_count: number; unsearchable_count: number; message: string;
}
