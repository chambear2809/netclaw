const JSON_MIME_TYPE = 'application/json';

function json(value) {
  return JSON.stringify(value);
}

function numeric(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function firstNumeric(...values) {
  return values.map(numeric).find((value) => value !== undefined);
}

export function canonicalChatMessages(messages, userMessage) {
  if (Array.isArray(messages) && messages.length) return messages;
  return [{ role: 'user', content: userMessage || '' }];
}

export function applySpanAttributes(span, attributes) {
  for (const [key, value] of Object.entries(attributes)) {
    if (value === undefined || value === null) continue;
    span.setAttribute(key, value);
  }
}

export function buildChatStartAttributes({ messages, userMessage, timestamp }) {
  const inputMessages = canonicalChatMessages(messages, userMessage);
  const serializedInput = json(inputMessages);

  return {
    // Galileo's OTLP provider requires the current OTel GenAI operation and
    // provider attributes to classify a custom span as an LLM invocation.
    'gen_ai.operation.name': 'chat',
    'gen_ai.provider.name': 'openai',
    'gen_ai.request.model': 'openclaw',

    // Current OpenTelemetry GenAI fields populate Galileo's canonical Input
    // column. The OpenInference fields make the same complete payload usable
    // by other compatible backends without removing the legacy attributes.
    'gen_ai.input.messages': serializedInput,
    'llm.input_messages': serializedInput,
    'input.value': serializedInput,
    'input.mime_type': JSON_MIME_TYPE,
    'openinference.span.kind': 'LLM',

    // Backward compatibility for existing Splunk searches and Galileo's
    // older OpenInference mapping.
    'gen_ai.system': 'openai',
    'gen_ai.request.prompt': serializedInput,
    'netclaw.chat.input': serializedInput,
    'netclaw.chat.input.message_count': inputMessages.length,
    'netclaw.chat.timestamp': timestamp,
  };
}

export function buildGatewayRequestAttributes(requestBody) {
  const serializedRequest = json(requestBody);
  const serializedMessages = json(requestBody.messages || []);
  return {
    'gen_ai.request.model': requestBody.model,
    'gen_ai.input.messages': serializedMessages,
    'llm.input_messages': serializedMessages,
    'input.value': serializedMessages,
    'gen_ai.request.prompt': serializedMessages,
    'netclaw.chat.gateway.request': serializedRequest,
    'netclaw.chat.gateway.request.stream': requestBody.stream === true,
    'netclaw.chat.gateway.request.message_count': Array.isArray(requestBody.messages)
      ? requestBody.messages.length
      : 0,
  };
}

function usageAttributes(usage, suppressCompatibilityPlaceholders = false) {
  if (!usage || typeof usage !== 'object') return {};

  const inputTokens = firstNumeric(usage.input_tokens, usage.prompt_tokens);
  const outputTokens = firstNumeric(usage.output_tokens, usage.completion_tokens);
  const totalTokens = firstNumeric(
    usage.total_tokens,
    inputTokens !== undefined && outputTokens !== undefined
      ? inputTokens + outputTokens
      : undefined,
  );
  const compatibilityPlaceholder = suppressCompatibilityPlaceholders
    && inputTokens === 0
    && outputTokens === 0
    && totalTokens === 0;
  const attributes = {
    'netclaw.chat.gateway.usage': json(usage),
    // OpenClaw's OpenAI-compatibility response currently hard-codes zeroes.
    // Preserve that raw payload for diagnosis, but do not publish the zeroes
    // as real GenAI metrics when transcript correlation is unavailable.
    'gen_ai.usage.input_tokens': compatibilityPlaceholder ? undefined : inputTokens,
    'gen_ai.usage.output_tokens': compatibilityPlaceholder ? undefined : outputTokens,
    'gen_ai.usage.prompt_tokens': compatibilityPlaceholder ? undefined : inputTokens,
    'gen_ai.usage.completion_tokens': compatibilityPlaceholder ? undefined : outputTokens,
    'gen_ai.usage.total_tokens': compatibilityPlaceholder ? undefined : totalTokens,
  };

  // Preserve every scalar usage field exposed by the OpenAI-compatible
  // gateway. Known token metrics above remain stable while newer fields such
  // as cached/reasoning tokens arrive without another instrumentation change.
  for (const [key, value] of Object.entries(usage)) {
    if (['string', 'number', 'boolean'].includes(typeof value)) {
      attributes[`netclaw.chat.gateway.usage.${key}`] = value;
    }
  }

  return attributes;
}

function openClawTelemetryAttributes(telemetry) {
  if (!telemetry || typeof telemetry !== 'object') return {};
  const aggregate = telemetry.aggregate || {};
  const modelCalls = Array.isArray(telemetry.modelCalls) ? telemetry.modelCalls : [];
  const stopReasons = modelCalls
    .map((call) => call?.stopReason)
    .filter((reason) => typeof reason === 'string' && reason);

  return {
    // A gateway run is Galileo's stable session boundary. Emit every supported
    // alias so the backend can resolve the session without relying on a header.
    'session.id': telemetry.sessionId,
    'gen_ai.conversation.id': telemetry.sessionId,
    'galileo.session.id': telemetry.sessionId,

    // The OpenAI compatibility response deliberately reports usage as zero.
    // These are the exact values persisted by OpenClaw for every model call.
    'gen_ai.request.model': telemetry.model,
    'gen_ai.response.model': telemetry.model,
    'gen_ai.response.id': telemetry.responseId,
    'gen_ai.response.finish_reasons': stopReasons.length ? stopReasons : undefined,
    'gen_ai.usage.input_tokens': numeric(aggregate.promptTokens),
    'gen_ai.usage.output_tokens': numeric(aggregate.outputTokens),
    'gen_ai.usage.prompt_tokens': numeric(aggregate.promptTokens),
    'gen_ai.usage.completion_tokens': numeric(aggregate.outputTokens),
    'gen_ai.usage.total_tokens': numeric(aggregate.totalTokens),
    'gen_ai.usage.cache_read_input_tokens': numeric(aggregate.cacheReadTokens),
    'gen_ai.usage.cache_creation_input_tokens': numeric(aggregate.cacheWriteTokens),

    // Mirror every available model/usage field into OpenInference as well as
    // OTel GenAI. Galileo supports both conventions and normalizes these into
    // its model, token, cache, and cost fields.
    'llm.system': 'openai',
    'llm.provider': telemetry.provider,
    'llm.model_name': telemetry.model,
    'llm.finish_reason': telemetry.stopReason,
    'llm.token_count.prompt': numeric(aggregate.promptTokens),
    'llm.token_count.completion': numeric(aggregate.outputTokens),
    'llm.token_count.total': numeric(aggregate.totalTokens),
    'llm.token_count.prompt_details.cache_read': numeric(aggregate.cacheReadTokens),
    'llm.token_count.prompt_details.cache_write': numeric(aggregate.cacheWriteTokens),
    'llm.cost.prompt': numeric(aggregate.costPromptUsd),
    'llm.cost.completion': numeric(aggregate.costOutputUsd),
    'llm.cost.total': numeric(aggregate.costUsd),
    'llm.cost.prompt_details.input': numeric(aggregate.costInputUsd),
    'llm.cost.prompt_details.cache_read': numeric(aggregate.costCacheReadUsd),
    'llm.cost.prompt_details.cache_write': numeric(aggregate.costCacheWriteUsd),
    'llm.cost.completion_details.output': numeric(aggregate.costOutputUsd),
    'netclaw.chat.openclaw.run_id': telemetry.runId,
    'netclaw.chat.openclaw.provider': telemetry.provider,
    'netclaw.chat.openclaw.model': telemetry.model,
    'netclaw.chat.openclaw.stop_reason': telemetry.stopReason,
    'netclaw.chat.openclaw.response_id': telemetry.responseId,
    'netclaw.chat.openclaw.model_call_count': numeric(telemetry.modelCallCount),
    'netclaw.chat.openclaw.duration_ms': numeric(telemetry.durationMs),
    'netclaw.chat.openclaw.cost_usd': numeric(aggregate.costUsd),
    'netclaw.chat.openclaw.usage': JSON.stringify(aggregate),
    'netclaw.chat.openclaw.model_calls': JSON.stringify(modelCalls),
  };
}

export function buildChatCompletionAttributes({
  responseText,
  gatewayResponse,
  gatewayResponseBody,
  gatewayStatusCode,
  gatewayDurationMs,
  fromGateway,
  openClawTelemetry,
}) {
  const outputMessages = [{ role: 'assistant', content: responseText }];
  const serializedOutput = json(outputMessages);
  const responseModel = gatewayResponse?.model || 'openclaw';
  const finishReasons = Array.isArray(gatewayResponse?.choices)
    ? gatewayResponse.choices
      .map((choice) => choice?.finish_reason)
      .filter((reason) => typeof reason === 'string' && reason)
    : [];

  return {
    // Current OpenTelemetry and OpenInference output fields populate
    // Galileo's canonical Output column with the full assistant response.
    'gen_ai.output.messages': serializedOutput,
    'llm.output_messages': serializedOutput,
    'output.value': serializedOutput,
    'output.mime_type': JSON_MIME_TYPE,

    // Keep legacy fields for consumers already querying them.
    'gen_ai.response.content': responseText,
    'gen_ai.response.model': responseModel,
    'gen_ai.response.id': gatewayResponse?.id,
    'gen_ai.response.finish_reasons': finishReasons.length ? finishReasons : undefined,
    'netclaw.chat.output': serializedOutput,
    'netclaw.chat.output.character_count': responseText.length,
    'netclaw.chat.gateway.response': gatewayResponseBody,
    'netclaw.chat.gateway.http.status_code': numeric(gatewayStatusCode),
    'netclaw.chat.gateway.duration_ms': numeric(gatewayDurationMs),
    'netclaw.chat.from_gateway': fromGateway,
    ...usageAttributes(
      gatewayResponse?.usage,
      gatewayResponse?.model === 'openclaw',
    ),
    // Deliberately last: exact OpenClaw transcript metadata supersedes the
    // compatibility endpoint's documented zero-valued usage placeholders.
    ...openClawTelemetryAttributes(openClawTelemetry),
  };
}

export function buildGatewayErrorAttributes(error) {
  if (!error) return {};
  return {
    'error.type': error.name || 'Error',
    'error.message': error.message || String(error),
    'netclaw.chat.gateway.error': true,
  };
}
