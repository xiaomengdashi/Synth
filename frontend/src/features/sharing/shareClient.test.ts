import assert from 'node:assert/strict';
import { test } from 'node:test';

test('repeated mounting submits a shared link only once while the request is pending', async (t) => {
  const { submitShare } = await import('./shareClient.ts');
  let calls = 0;
  let complete!: (value: Response) => void;
  t.mock.method(globalThis, 'fetch', async (_url: string, init: RequestInit) => {
    calls += 1;
    assert.deepEqual(JSON.parse(init.body as string), { text: '文章 https://x.com/a/status/123' });
    return await new Promise<Response>((resolve) => { complete = resolve; });
  });
  const first = submitShare({ text: '文章 https://x.com/a/status/123' });
  const second = submitShare({ text: '文章 https://x.com/a/status/123' });
  complete(Response.json({ task_id: 'saved-task', status: 'pending' }));
  assert.equal((await first).task_id, 'saved-task');
  assert.equal((await second).task_id, 'saved-task');
  assert.equal(calls, 1);
});

test('an invalid share surfaces the actionable server error', async (t) => {
  const { submitShare } = await import('./shareClient.ts');
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: '没有找到有效的 X 或微信文章链接' }, { status: 400 }));
  await assert.rejects(submitShare({ text: 'invalid' }), /没有找到有效的 X 或微信文章链接/);
});

test('polling delivers the saved article and stops after completion', async (t) => {
  const { watchSharedTask } = await import('./shareClient.ts');
  const replies = [
    { status: 'processing', current_step: '读取长文' },
    { status: 'completed', article_id: 'saved-article' },
  ];
  t.mock.method(globalThis, 'fetch', async () => Response.json(replies.shift()));
  const progress: string[] = [];
  const result = await watchSharedTask('task', (data) => progress.push(data.status), new AbortController().signal, 0, 4);
  assert.equal(result.article_id, 'saved-article');
  assert.deepEqual(progress, ['processing', 'completed']);
});

test('a polling deadline does not report a running backend task as failed', async (t) => {
  const { watchSharedTask } = await import('./shareClient.ts');
  t.mock.method(globalThis, 'fetch', async () => Response.json({ status: 'processing' }));
  const result = await watchSharedTask('task', () => {}, new AbortController().signal, 0, 2);
  assert.equal(result.status, 'processing');
});

test('failed task progress preserves the failure reason for retry', async (t) => {
  const { watchSharedTask } = await import('./shareClient.ts');
  t.mock.method(globalThis, 'fetch', async () => Response.json({ status: 'failed', current_step: 'X 登录态已过期' }));
  const result = await watchSharedTask('task', () => {}, new AbortController().signal, 0, 2);
  assert.equal(result.status, 'failed');
  assert.equal(result.current_step, 'X 登录态已过期');
});
