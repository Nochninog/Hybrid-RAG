import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { ApiError, citationMarkdown, request, validateFile } from '../src/api.js';

const fetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = fetch; });

test('file validation rejects unsupported, empty and oversize inputs', () => {
  for (const file of [null, { name: 'a.docx', size: 1 }, { name: 'a.pdf', size: 0 }, { name: 'a.md', size: 20 * 1024 * 1024 + 1 }]) {
    assert.ok(validateFile(file));
  }
  assert.equal(validateFile({ name: 'a.PDF', size: 20 * 1024 * 1024 }), '');
});

test('citations link only existing sources and preserve ordinary markdown links', () => {
  assert.equal(citationMarkdown('Факт [1, 2]. [9] [1](https://example.com)', [{ source_id: 1 }, { source_id: 2 }]),
    'Факт [1](#source-1) [2](#source-2). [9] [1](https://example.com)');
});

test('operation errors preserve saved IDs for recovery', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 502, json: async () => ({ detail: { stage: 'index_wiki', wiki_page_id: 7, message: 'Ошибка' } }) });
  await assert.rejects(() => request('knowledge', '/wiki-pages'), error => error instanceof ApiError && error.detail.wiki_page_id === 7 && error.status === 502);
});

test('proxy HTML errors and lost responses give meaningful errors', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 504, json: async () => { throw Error('html'); } });
  await assert.rejects(() => request('search', '/questions'), /Проверьте результат/);
  globalThis.fetch = async () => { throw Error('network'); };
  await assert.rejects(() => request('knowledge', '/documents'), /проверьте её результат/);
});

test('multipart payload passes through without forced JSON headers', async () => {
  const form = new FormData(); form.append('file', new Blob(['content']), 'file.md');
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/knowledge/documents');
    assert.equal(options.body, form);
    assert.equal(options.headers, undefined);
    return { ok: true, json: async () => ({ document_id: 4 }) };
  };
  assert.equal((await request('knowledge', '/documents', { method: 'POST', body: form })).document_id, 4);
});
