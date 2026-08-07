import test from 'node:test';
import assert from 'node:assert/strict';

import {
  applySpanAttributes,
  buildChatCompletionAttributes,
  buildChatStartAttributes,
  buildGatewayErrorAttributes,
  buildGatewayRequestAttributes,
} from './chat-telemetry.js';

test('chat start emits Galileo-required GenAI input fields without redaction', () => {
  const messages = [
    { role: 'user', content: 'show the complete input' },
    { role: 'assistant', content: 'previous response' },
  ];
  const attributes = buildChatStartAttributes({
    messages,
    userMessage: '',
    timestamp: '2026-08-07T15:00:00.000Z',
  });

  assert.equal(attributes['gen_ai.operation.name'], 'chat');
  assert.equal(attributes['gen_ai.provider.name'], 'openai');
  assert.equal(attributes['openinference.span.kind'], 'LLM');
  assert.deepEqual(JSON.parse(attributes['gen_ai.input.messages']), messages);
  assert.equal(attributes['gen_ai.input.messages'], attributes['llm.input_messages']);
  assert.equal(attributes['gen_ai.input.messages'], attributes['input.value']);
  assert.equal(attributes['gen_ai.input.messages'], attributes['gen_ai.request.prompt']);
});

test('gateway request replaces canonical input with the exact messages sent upstream', () => {
  const requestBody = {
    model: 'openclaw',
    messages: [{ role: 'user', content: 'actual upstream input' }],
    stream: false,
  };
  const attributes = buildGatewayRequestAttributes(requestBody);

  assert.deepEqual(JSON.parse(attributes['gen_ai.input.messages']), requestBody.messages);
  assert.deepEqual(JSON.parse(attributes['netclaw.chat.gateway.request']), requestBody);
  assert.equal(attributes['netclaw.chat.gateway.request.message_count'], 1);
});

test('completion emits full canonical output, gateway payload, and every token metric', () => {
  const gatewayResponse = {
    id: 'chatcmpl-test',
    model: 'gpt-test',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: 'complete output' } }],
    usage: {
      prompt_tokens: 11,
      completion_tokens: 7,
      total_tokens: 18,
      cached_tokens: 3,
    },
  };
  const gatewayResponseBody = JSON.stringify(gatewayResponse);
  const attributes = buildChatCompletionAttributes({
    responseText: 'complete output',
    gatewayResponse,
    gatewayResponseBody,
    gatewayStatusCode: 200,
    gatewayDurationMs: 123.5,
    fromGateway: true,
    openClawTelemetry: {
      runId: 'chatcmpl-test',
      sessionId: 'session-test',
      provider: 'bridgeit',
      model: 'gpt-4o-mini',
      stopReason: 'stop',
      responseId: 'provider-response-test',
      modelCallCount: 2,
      durationMs: 120,
      aggregate: {
        inputTokens: 12,
        outputTokens: 9,
        cacheReadTokens: 20,
        cacheWriteTokens: 2,
        promptTokens: 34,
        totalTokens: 43,
        costInputUsd: 0.004,
        costOutputUsd: 0.003,
        costCacheReadUsd: 0.001,
        costCacheWriteUsd: 0.002,
        costPromptUsd: 0.007,
        costUsd: 0.01,
      },
      modelCalls: [
        { model: 'gpt-4o-mini', stopReason: 'toolUse', usage: { input: 12, output: 2 } },
        { model: 'gpt-4o-mini', stopReason: 'stop', usage: { input: 0, output: 7, cacheRead: 20, cacheWrite: 2 } },
      ],
    },
  });

  assert.deepEqual(JSON.parse(attributes['gen_ai.output.messages']), [
    { role: 'assistant', content: 'complete output' },
  ]);
  assert.equal(attributes['gen_ai.output.messages'], attributes['llm.output_messages']);
  assert.equal(attributes['gen_ai.output.messages'], attributes['output.value']);
  assert.equal(attributes['gen_ai.response.id'], 'provider-response-test');
  assert.equal(attributes['gen_ai.request.model'], 'gpt-4o-mini');
  assert.deepEqual(attributes['gen_ai.response.finish_reasons'], ['toolUse', 'stop']);
  assert.equal(attributes['session.id'], 'session-test');
  assert.equal(attributes['gen_ai.conversation.id'], 'session-test');
  assert.equal(attributes['galileo.session.id'], 'session-test');
  assert.equal(attributes['gen_ai.usage.input_tokens'], 34);
  assert.equal(attributes['gen_ai.usage.output_tokens'], 9);
  assert.equal(attributes['gen_ai.usage.total_tokens'], 43);
  assert.equal(attributes['gen_ai.usage.cache_read_input_tokens'], 20);
  assert.equal(attributes['llm.model_name'], 'gpt-4o-mini');
  assert.equal(attributes['llm.provider'], 'bridgeit');
  assert.equal(attributes['llm.finish_reason'], 'stop');
  assert.equal(attributes['llm.token_count.prompt'], 34);
  assert.equal(attributes['llm.token_count.completion'], 9);
  assert.equal(attributes['llm.token_count.total'], 43);
  assert.equal(attributes['llm.token_count.prompt_details.cache_read'], 20);
  assert.equal(attributes['llm.token_count.prompt_details.cache_write'], 2);
  assert.equal(attributes['llm.cost.prompt'], 0.007);
  assert.equal(attributes['llm.cost.completion'], 0.003);
  assert.equal(attributes['llm.cost.total'], 0.01);
  assert.equal(attributes['netclaw.chat.gateway.usage.cached_tokens'], 3);
  assert.equal(attributes['netclaw.chat.gateway.response'], gatewayResponseBody);
  assert.equal(attributes['netclaw.chat.openclaw.model_call_count'], 2);
});

test('completion does not invent unavailable usage metrics', () => {
  const attributes = buildChatCompletionAttributes({
    responseText: 'fallback output',
    gatewayResponse: null,
    gatewayResponseBody: 'upstream unavailable',
    gatewayStatusCode: 503,
    gatewayDurationMs: 50,
    fromGateway: false,
  });

  assert.equal(attributes['gen_ai.usage.input_tokens'], undefined);
  assert.equal(attributes['gen_ai.usage.output_tokens'], undefined);
  assert.equal(attributes['gen_ai.usage.total_tokens'], undefined);
});

test('OpenClaw compatibility zeroes remain raw fields, not token metrics', () => {
  const attributes = buildChatCompletionAttributes({
    responseText: 'output without correlated metadata',
    gatewayResponse: {
      id: 'chatcmpl-placeholder',
      model: 'openclaw',
      choices: [],
      usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    },
    gatewayResponseBody: '{}',
    gatewayStatusCode: 200,
    gatewayDurationMs: 25,
    fromGateway: true,
  });

  assert.deepEqual(JSON.parse(attributes['netclaw.chat.gateway.usage']), {
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
  });
  assert.equal(attributes['netclaw.chat.gateway.usage.total_tokens'], 0);
  assert.equal(attributes['gen_ai.usage.input_tokens'], undefined);
  assert.equal(attributes['gen_ai.usage.output_tokens'], undefined);
  assert.equal(attributes['gen_ai.usage.total_tokens'], undefined);
});

test('attribute application omits nullish values and records safe error fields', () => {
  const recorded = {};
  const span = { setAttribute: (key, value) => { recorded[key] = value; } };
  applySpanAttributes(span, { present: 0, missing: undefined, empty: null });
  applySpanAttributes(span, buildGatewayErrorAttributes(new TypeError('gateway failed')));

  assert.deepEqual(recorded, {
    present: 0,
    'error.type': 'TypeError',
    'error.message': 'gateway failed',
    'netclaw.chat.gateway.error': true,
  });
});
