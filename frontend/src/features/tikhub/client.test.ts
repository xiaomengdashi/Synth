import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildParameters, requestJson, schemaType } from './client.ts';

test('query parameters preserve long IDs and handle false, zero and omitted optional values', () => {
  assert.deepEqual(buildParameters([
    { name: 'tweet_id', required: true, schema: { type: 'string' } },
    { name: 'cursor', required: false, schema: { type: 'integer' } },
    { name: 'raw', required: false, schema: { type: 'boolean' } },
    { name: 'optional', required: false, schema: { type: 'string' } },
  ], { tweet_id: '1808168603721650364', cursor: '0', raw: 'false', optional: '' }), {
    tweet_id: '1808168603721650364', cursor: 0, raw: false,
  });
});

test('missing required fields and invalid numbers fail before a paid query', () => {
  assert.throws(() => buildParameters([{ name: 'id', required: true, schema: { type: 'string' } }], { id: ' ' }), /id/);
  assert.throws(() => buildParameters([{ name: 'count', schema: { type: 'integer' } }], { count: '1.5' }), /count/);
  assert.throws(() => buildParameters([{ name: 'count', schema: { type: 'integer' } }], { count: '1808168603721650364' }), /count/);
  assert.throws(() => buildParameters([{ name: 'items', schema: { type: 'array' } }], { items: '[1808168603721650364]' }), /精度/);
});

test('nullable and structured parameters are parsed correctly', () => {
  assert.equal(schemaType({ anyOf: [{ type: 'integer' }, { type: 'null' }] }), 'integer');
  assert.deepEqual(buildParameters([{ name: 'ids', schema: { type: 'array' } }], { ids: '["123", "456"]' }), { ids: ['123', '456'] });
});

test('union schemas retain string IDs and allow fractional numeric inputs', () => {
  assert.deepEqual(buildParameters([
    { name: 'goods_ctr_min', schema: { anyOf: [{ type: 'integer' }, { type: 'number' }, { type: 'string' }] } },
  ], { goods_ctr_min: '0.5' }), { goods_ctr_min: '0.5' });
  assert.deepEqual(buildParameters([
    { name: 'mid', schema: { anyOf: [{ type: 'integer' }, { type: 'string' }] } },
  ], { mid: '1808168603721650364' }), { mid: '1808168603721650364' });
  assert.deepEqual(buildParameters([
    { name: 'ratio', schema: { anyOf: [{ type: 'integer' }, { type: 'number' }] } },
  ], { ratio: '0.5' }), { ratio: 0.5 });
});

test('HTTP errors including validation arrays and non-JSON responses stay readable', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('<html>Bad gateway</html>', { status: 502 });
    await assert.rejects(requestJson('/test'), /502/);
    globalThis.fetch = async () => Response.json({ detail: [{ msg: 'Missing field' }] }, { status: 422 });
    await assert.rejects(requestJson('/test'), /Missing field/);
    globalThis.fetch = async () => Response.json({ configured: false });
    assert.deepEqual(await requestJson('/test'), { configured: false });
  } finally {
    globalThis.fetch = original;
  }
});
