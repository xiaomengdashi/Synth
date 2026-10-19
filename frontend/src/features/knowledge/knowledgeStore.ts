import { create } from 'zustand';
import { knowledgeClient } from './client.ts';
import { mergeTurn, applyConversationSnapshot } from './lib/conversationState.ts';
import type { ConversationCache, ConversationSummary, KnowledgeTurn } from './types';

interface KnowledgeState {
  conversations: ConversationSummary[]; total: number; byId: ConversationCache;
  pendingById: Record<string, boolean>; errorsById: Record<string, string>;
  loadList: (reset?: boolean) => Promise<void>;
  createConversation: () => Promise<string>;
  loadConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  sendQuestion: (id: string, question: string) => Promise<void>;
}

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  conversations: [], total: 0, byId: {}, pendingById: {}, errorsById: {},
  async loadList(reset = true) {
    const result = await knowledgeClient.list(30, reset ? 0 : get().conversations.length);
    set(state => ({total: result.total, conversations: reset ? result.data : [...state.conversations, ...result.data.filter(c => !state.conversations.some(old => old.id === c.id))]}));
  },
  async createConversation() {
    const conversation = await knowledgeClient.create();
    set(state => ({conversations:[conversation, ...state.conversations], total:state.total + 1,
      byId:{...state.byId, [conversation.id]:{conversation, turns:[], lastMutationAt:0}}}));
    return conversation.id;
  },
  async loadConversation(id) {
    const startedAt = Date.now();
    const result = await knowledgeClient.get(id);
    set(state => ({byId: applyConversationSnapshot(state.byId, result, startedAt)}));
  },
  async deleteConversation(id) {
    await knowledgeClient.remove(id);
    set(state => {
      const byId = {...state.byId}; delete byId[id];
      return {byId, conversations:state.conversations.filter(c => c.id !== id), total:Math.max(0, state.total - 1)};
    });
  },
  async sendQuestion(id, question) {
    if (get().pendingById[id]) return;
    const requestId = crypto.randomUUID();
    const turn: KnowledgeTurn = {id:requestId, request_id:requestId, conversation_id:id, question, answer:'',
      status:'pending', insufficient_evidence:false, sources:[], error_message:'', created_at:new Date().toISOString(), completed_at:''};
    set(state => ({pendingById:{...state.pendingById,[id]:true}, errorsById:{...state.errorsById,[id]:''},
      byId:mergeTurn(state.byId,id,turn,Date.now())}));
    try {
      const result = await knowledgeClient.send(id, question, requestId);
      set(state => ({byId:mergeTurn(state.byId,id,result,Date.now())}));
      // Preserve loaded list pages while moving this conversation to the top.
      const startedAt = Date.now();
      await knowledgeClient.get(id).then(detail => {
        set(state => ({byId:applyConversationSnapshot(state.byId,detail,startedAt),
          conversations:[detail.conversation,...state.conversations.filter(c => c.id !== id)]}));
      }).catch(() => { /* The answer is saved; a list refresh failure must not discard it. */ });
    } catch (error) {
      const message = error instanceof Error ? error.message : '提问未完成，请稍后重试。';
      set(state => ({errorsById:{...state.errorsById,[id]:message},
        byId:mergeTurn(state.byId,id,{...turn,status:'failed',error_message:message},Date.now())}));
      await get().loadConversation(id).catch(() => {});
      throw error;
    } finally {
      set(state => ({pendingById:{...state.pendingById,[id]:false}}));
    }
  },
}));
