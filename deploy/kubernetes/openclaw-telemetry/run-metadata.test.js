import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { extractRunMetadata, findRunMetadata } from './run-metadata.js';

const RUN_ID = 'chatcmpl_12345678-1234-1234-1234-123456789abc';

function fixtureRows() {
  return [
    { type: 'message', timestamp: '2026-08-07T15:00:00.000Z', message: { role: 'user', content: 'not returned by metadata route' } },
    {
      type: 'message',
      timestamp: '2026-08-07T15:00:01.000Z',
      message: {
        role: 'assistant', provider: 'bridgeit', model: 'gpt-4o-mini', api: 'openai-completions',
        stopReason: 'toolUse', responseId: 'response-1', timestamp: 1786114800000,
        content: [{ type: 'toolCall', name: 'private_tool', arguments: { secret: 'not returned' } }],
        usage: {
          input: 100, output: 10, cacheRead: 20, cacheWrite: 5, totalTokens: 135,
          cost: { input: 0.04, output: 0.03, cacheRead: 0.01, cacheWrite: 0.02, total: 0.1 },
        },
      },
    },
    { type: 'message', message: { role: 'toolResult', content: 'private tool result' } },
    {
      type: 'message',
      timestamp: '2026-08-07T15:00:02.000Z',
      message: {
        role: 'assistant', provider: 'bridgeit', model: 'gpt-4o-mini', api: 'openai-completions',
        stopReason: 'stop', responseId: 'response-2', timestamp: 1786114801000,
        content: [{ type: 'text', text: 'not returned by metadata route' }],
        usage: {
          input: 8, output: 4, cacheRead: 125, cacheWrite: 0, totalTokens: 137,
          cost: { input: 0.002, output: 0.008, cacheRead: 0.01, cacheWrite: 0, total: 0.02 },
        },
      },
    },
    {
      type: 'custom',
      customType: 'openclaw:bootstrap-context:full',
      timestamp: '2026-08-07T15:00:02.000Z',
      data: { timestamp: 1786114802000, runId: RUN_ID, sessionId: 'session-123' },
    },
  ];
}

test('extracts exact model metadata while excluding message and tool content', () => {
  const metadata = extractRunMetadata(fixtureRows(), RUN_ID);
  const serialized = JSON.stringify(metadata);

  assert.equal(metadata.sessionId, 'session-123');
  assert.equal(metadata.modelCallCount, 2);
  assert.equal(metadata.durationMs, 2000);
  assert.deepEqual(metadata.aggregate, {
    inputTokens: 108,
    outputTokens: 14,
    cacheReadTokens: 145,
    cacheWriteTokens: 5,
    promptTokens: 258,
    totalTokens: 272,
    costInputUsd: 0.042,
    costOutputUsd: 0.038,
    costCacheReadUsd: 0.02,
    costCacheWriteUsd: 0.02,
    costPromptUsd: 0.082,
    costUsd: 0.12000000000000001,
  });
  assert.equal(serialized.includes('private_tool'), false);
  assert.equal(serialized.includes('private tool result'), false);
  assert.equal(serialized.includes('not returned by metadata route'), false);
});

test('finds a completed run in the bounded session directory', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'netclaw-telemetry-'));
  try {
    fs.writeFileSync(
      path.join(tempDir, 'session.jsonl'),
      `${fixtureRows().map((row) => JSON.stringify(row)).join('\n')}\n`,
    );
    const metadata = findRunMetadata(tempDir, RUN_ID);
    assert.equal(metadata.responseId, 'response-2');
    assert.equal(metadata.stopReason, 'stop');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('supports a legacy marker written before its model calls', () => {
  const rows = fixtureRows();
  const marker = rows.pop();
  rows.unshift(marker);
  const metadata = extractRunMetadata(rows, RUN_ID);

  assert.equal(metadata.modelCallCount, 2);
  assert.equal(metadata.responseId, 'response-2');
});

test('rejects malformed run identifiers before reading files', () => {
  assert.equal(findRunMetadata('/does/not/exist', '../../secret'), null);
});
