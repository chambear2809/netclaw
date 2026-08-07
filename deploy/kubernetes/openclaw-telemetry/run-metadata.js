import fs from 'node:fs';
import path from 'node:path';

const RUN_ID_PATTERN = /^chatcmpl_[0-9a-f-]{36}$/i;

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function parseLine(line) {
  try {
    return JSON.parse(line);
  } catch {
    return null;
  }
}

function runMarker(row, runId) {
  return row?.type === 'custom'
    && row?.data?.runId === runId
    && typeof row?.data?.sessionId === 'string';
}

function anyRunMarker(row) {
  return row?.type === 'custom'
    && typeof row?.data?.runId === 'string'
    && typeof row?.data?.sessionId === 'string';
}

function safeUsage(usage) {
  if (!usage || typeof usage !== 'object') return null;
  return JSON.parse(JSON.stringify(usage));
}

function aggregateCalls(modelCalls) {
  return modelCalls.reduce((aggregate, call) => {
    const usage = call.usage || {};
    const cost = usage.cost || {};
    const input = finite(usage.input);
    const cacheRead = finite(usage.cacheRead);
    const cacheWrite = finite(usage.cacheWrite);
    aggregate.inputTokens += input;
    aggregate.outputTokens += finite(usage.output);
    aggregate.cacheReadTokens += cacheRead;
    aggregate.cacheWriteTokens += cacheWrite;
    aggregate.promptTokens += input + cacheRead + cacheWrite;
    aggregate.totalTokens += finite(usage.totalTokens);
    aggregate.costInputUsd += finite(cost.input);
    aggregate.costOutputUsd += finite(cost.output);
    aggregate.costCacheReadUsd += finite(cost.cacheRead);
    aggregate.costCacheWriteUsd += finite(cost.cacheWrite);
    aggregate.costPromptUsd += finite(cost.input)
      + finite(cost.cacheRead)
      + finite(cost.cacheWrite);
    aggregate.costUsd += finite(cost.total);
    return aggregate;
  }, {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    promptTokens: 0,
    totalTokens: 0,
    costInputUsd: 0,
    costOutputUsd: 0,
    costCacheReadUsd: 0,
    costCacheWriteUsd: 0,
    costPromptUsd: 0,
    costUsd: 0,
  });
}

function epochMs(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? parsed : undefined;
}

function durationMs(start, end) {
  const startMs = epochMs(start);
  const endMs = epochMs(end);
  return Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs
    ? endMs - startMs
    : undefined;
}

function modelCallsFrom(rows) {
  return rows.flatMap((row) => {
    const message = row?.message;
    if (row?.type !== 'message' || message?.role !== 'assistant' || !message?.usage) return [];
    return [{
      provider: message.provider ?? null,
      model: message.model ?? null,
      api: message.api ?? null,
      stopReason: message.stopReason ?? null,
      responseId: message.responseId ?? null,
      // The message timestamp is the provider-call start in current OpenClaw
      // transcripts. The row timestamp is when the completed response was
      // persisted and is therefore the useful completion timestamp.
      timestamp: row.timestamp ?? message.timestamp ?? null,
      usage: safeUsage(message.usage),
    }];
  });
}

export function extractRunMetadata(rows, runId) {
  const markerIndex = rows.findIndex((row) => runMarker(row, runId));
  if (markerIndex < 0) return null;

  const marker = rows[markerIndex];
  const previousMarkerIndex = rows
    .slice(0, markerIndex)
    .findLastIndex(anyRunMarker);
  const beforeMarker = rows.slice(previousMarkerIndex + 1, markerIndex);
  const nextMarkerOffset = rows.slice(markerIndex + 1).findIndex(anyRunMarker);
  const afterMarker = rows.slice(
    markerIndex + 1,
    nextMarkerOffset < 0 ? rows.length : markerIndex + 1 + nextMarkerOffset,
  );

  // OpenClaw writes openclaw:bootstrap-context:full as a completion boundary:
  // the user/model/tool rows precede it. Older fixtures and possible upstream
  // versions may write the marker first, so retain a bounded fallback after it.
  const beforeCalls = modelCallsFrom(beforeMarker);
  const runRows = beforeCalls.length ? beforeMarker : afterMarker;
  const modelCalls = beforeCalls.length ? beforeCalls : modelCallsFrom(afterMarker);

  if (!modelCalls.length) return null;
  const finalCall = modelCalls.at(-1);
  const firstUser = runRows.find(
    (row) => row?.type === 'message' && row?.message?.role === 'user',
  );
  const startedAt = firstUser?.timestamp
    ?? firstUser?.message?.timestamp
    ?? runRows[0]?.timestamp;
  const completedAt = beforeCalls.length
    ? (marker.timestamp ?? marker.data.timestamp ?? finalCall.timestamp)
    : finalCall.timestamp;
  return {
    runId,
    sessionId: marker.data.sessionId,
    provider: finalCall.provider,
    model: finalCall.model,
    stopReason: finalCall.stopReason,
    responseId: finalCall.responseId,
    modelCallCount: modelCalls.length,
    durationMs: durationMs(startedAt, completedAt),
    aggregate: aggregateCalls(modelCalls),
    modelCalls,
  };
}

export function findRunMetadata(sessionDir, runId, maxFiles = 200) {
  if (!RUN_ID_PATTERN.test(runId || '')) return null;
  let candidates;
  try {
    candidates = fs.readdirSync(sessionDir)
      .filter((name) => name.endsWith('.jsonl'))
      .map((name) => ({
        name,
        mtime: fs.statSync(path.join(sessionDir, name)).mtimeMs,
      }))
      .sort((left, right) => right.mtime - left.mtime)
      .slice(0, maxFiles);
  } catch {
    return null;
  }

  for (const candidate of candidates) {
    const file = path.join(sessionDir, candidate.name);
    let text;
    try {
      text = fs.readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    if (!text.includes(runId)) continue;
    const rows = text.split('\n').filter(Boolean).map(parseLine).filter(Boolean);
    const metadata = extractRunMetadata(rows, runId);
    if (metadata) return metadata;
  }
  return null;
}
