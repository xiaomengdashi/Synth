import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeTurn, applyConversationSnapshot } from './conversationState.ts';
import type { ConversationCache, KnowledgeTurn } from '../types.ts';

const turn = (cid: string, id = 'turn', status = 'completed') => ({id, conversation_id: cid, request_id: 'request', question: 'Redis', answer: '答案[1]', status, insufficient_evidence: false, sources: [], error_message: '', created_at: '', completed_at: ''}) as KnowledgeTurn;
const cache = (): ConversationCache => ({a: {conversation: {id:'a', title:'A', created_at:'', updated_at:''}, turns:[], lastMutationAt:0}, b: {conversation: {id:'b', title:'B', created_at:'', updated_at:''}, turns:[], lastMutationAt:0}});

test('completion for A never overwrites B', () => {
  const before = cache();
  const after = mergeTurn(before, 'a', turn('a'), 100);
  assert.equal(after.b, before.b);
  assert.equal(after.b.turns.length, 0);
  assert.equal(after.a.turns[0].answer, '答案[1]');
});
test('stale snapshot preserves newer completed turn', () => {
  const current = mergeTurn(cache(), 'a', turn('a'), 100);
  const after = applyConversationSnapshot(current, {conversation: current.a.conversation, turns: []}, 50);
  assert.equal(after.a.turns[0].status, 'completed');
});
test('server result replaces optimistic request and duplicate completions', () => {
  let current = mergeTurn(cache(), 'a', turn('a', 'optimistic', 'pending'), 20);
  current = mergeTurn(current, 'a', turn('a', 'server'), 40);
  current = mergeTurn(current, 'a', turn('a', 'server'), 50);
  assert.equal(current.a.turns.length, 1);
  assert.equal(current.a.turns[0].id, 'server');
});
test('a read racing the first POST preserves the unsaved optimistic question', () => {
  const current = mergeTurn(cache(), 'a', turn('a','optimistic','pending'), 20);
  const next = applyConversationSnapshot(current, {conversation:current.a.conversation,turns:[]}, 30);
  assert.equal(next.a.turns.length, 1);
  assert.equal(next.a.turns[0].question, 'Redis');
});
