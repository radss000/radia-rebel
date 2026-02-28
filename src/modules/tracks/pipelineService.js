const { URL } = require('url');

const pipelineApiUrl = process.env.PIPELINE_API_URL || 'http://localhost:8000';

const fetchFn = globalThis.fetch
  ? globalThis.fetch.bind(globalThis)
  : ((...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args)));

function normaliseUrl(endpoint) {
  const base = pipelineApiUrl.replace(/\/$/, '');
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint;
  }
  return `${base}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
}

exports.ingestTrack = async function ingestTrack(payload) {
  if (!payload?.audioUrl) {
    throw new Error('Missing audioUrl for pipeline ingestion');
  }

  const body = {
    mongo_track_id: payload.mongoTrackId,
    title: payload.title,
    artist: payload.artist,
    genre: payload.genre,
    tags: payload.tags,
    description: payload.description,
    duration_seconds: payload.durationSeconds,
    audio_url: payload.audioUrl
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(process.env.PIPELINE_TIMEOUT_MS || 60000));

  const response = await fetchFn(normaliseUrl('/api/tracks/ingest'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body),
    signal: controller.signal
  });

  clearTimeout(timeout);

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Pipeline responded with ${response.status}: ${detail}`);
  }

  return response.json();
};
