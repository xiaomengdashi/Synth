import type { ConversationCache, ConversationDetail, KnowledgeTurn } from '../types.ts';

export function mergeTurn(cache: ConversationCache, conversationId: string, turn: KnowledgeTurn, receivedAt: number): ConversationCache {
  const current = cache[conversationId];
  if (!current) return cache;
  const turns = [...current.turns];
  const index = turns.findIndex(t => t.id === turn.id || t.request_id === turn.request_id);
  if (index < 0) turns.push(turn); else turns[index] = turn;
  return {...cache, [conversationId]: {...current, turns, lastMutationAt: receivedAt}};
}

export function applyConversationSnapshot(cache: ConversationCache, snapshot: ConversationDetail, startedAt: number): ConversationCache {
  const id = snapshot.conversation.id;
  if (cache[id]?.lastMutationAt > startedAt) return cache;
  const localPending = (cache[id]?.turns || []).filter(turn => turn.status === 'pending'
    && !snapshot.turns.some(saved => saved.request_id === turn.request_id));
  return {...cache, [id]: {...snapshot, turns:[...snapshot.turns,...localPending], lastMutationAt: cache[id]?.lastMutationAt || 0}};
}
