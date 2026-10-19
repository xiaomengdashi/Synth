import test from 'node:test';
import assert from 'node:assert/strict';
import { knowledgeClient } from '../client.ts';
import { useKnowledgeStore } from '../knowledgeStore.ts';
import type { KnowledgeTurn } from '../types.ts';

test('a failed metadata refresh never discards a completed answer', async t => {
  useKnowledgeStore.setState({byId:{a:{conversation:{id:'a',title:'A',created_at:'',updated_at:''},turns:[],lastMutationAt:0}},conversations:[],total:1,pendingById:{},errorsById:{}});
  t.mock.method(knowledgeClient, 'send', async (_id, question, requestId) => ({id:'saved', conversation_id:'a',request_id:requestId,question,answer:'已完成的答案[1]',status:'completed',sources:[],insufficient_evidence:false,error_message:'',created_at:'',completed_at:''} as KnowledgeTurn));
  t.mock.method(knowledgeClient, 'get', async () => {throw new Error('metadata network failure');});
  await useKnowledgeStore.getState().sendQuestion('a','问题');
  const state = useKnowledgeStore.getState();
  assert.equal(state.byId.a.turns[0].status, 'completed');
  assert.equal(state.byId.a.turns[0].answer, '已完成的答案[1]');
  assert.equal(state.pendingById.a, false);
});
