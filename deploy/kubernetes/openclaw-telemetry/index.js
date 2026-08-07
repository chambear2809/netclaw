import path from 'node:path';

import { findRunMetadata } from './run-metadata.js';

const MAX_BODY_BYTES = 4096;

async function readJsonBody(request) {
  let body = '';
  for await (const chunk of request) {
    body += chunk;
    if (Buffer.byteLength(body) > MAX_BODY_BYTES) throw new Error('request body too large');
  }
  return JSON.parse(body || '{}');
}

function sendJson(response, statusCode, payload) {
  response.statusCode = statusCode;
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  response.end(JSON.stringify(payload));
}

export default {
  id: 'netclaw-telemetry',
  name: 'NetClaw Telemetry Metadata',
  description: 'Authenticated, content-free model usage lookup for a completed OpenClaw run.',
  register(api) {
    api.registerHttpRoute({
      path: '/plugins/netclaw/telemetry/run',
      auth: 'gateway',
      match: 'exact',
      handler: async (request, response) => {
        if (request.method !== 'POST') {
          sendJson(response, 405, { error: 'method not allowed' });
          return true;
        }

        let body;
        try {
          body = await readJsonBody(request);
        } catch {
          sendJson(response, 400, { error: 'invalid JSON body' });
          return true;
        }

        const sessionDir = path.join(
          process.env.HOME || '/home/node',
          '.openclaw',
          'agents',
          'main',
          'sessions',
        );
        const metadata = findRunMetadata(sessionDir, body.runId);
        if (!metadata) {
          sendJson(response, 404, { error: 'run metadata not found' });
          return true;
        }

        sendJson(response, 200, metadata);
        return true;
      },
    });
  },
};
