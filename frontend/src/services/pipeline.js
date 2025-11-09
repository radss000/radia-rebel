import { apiRequest } from './api';

const DEFAULT_BROWSER_ORIGIN =
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000';
const DEFAULT_API_BASE = (process.env.REACT_APP_API_URL || DEFAULT_BROWSER_ORIGIN).replace(/\/$/, '');
const DEFAULT_PIPELINE_BASE = (
  process.env.REACT_APP_PIPELINE_API_URL ||
  'http://localhost:8000'
).replace(/\/$/, '');

/**
 * Perform a fetch against the Python pipeline API.
 * Automatically attaches the auth token (if any) and JSON headers by default.
 */
async function pipelineRequest(endpoint, options = {}) {
  const url = `${DEFAULT_PIPELINE_BASE}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };

  if (options.body instanceof FormData) {
    delete headers['Content-Type'];
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const requestInit = {
    ...options,
    headers
  };

  const response = await fetch(url, requestInit);

  let data = null;
  const isJson = response.headers.get('content-type')?.includes('application/json');
  if (isJson) {
    data = await response.json();
  } else {
    const text = await response.text();
    data = text ? { detail: text } : null;
  }

  if (!response.ok) {
    const message = data?.detail || data?.message || 'Pipeline request failed';
    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

/**
 * Search for tracks through the pipeline API.
 */
export async function searchPipelineTracks(query, limit = 10) {
  if (!query || !query.trim()) {
    return { query, results: [], count: 0 };
  }

  const params = new URLSearchParams({
    q: query.trim(),
    limit: String(limit)
  });

  return pipelineRequest(`/api/search?${params.toString()}`, {
    method: 'GET'
  });
}

/**
 * Fetch detailed metadata for a specific pipeline track.
 */
export async function getPipelineTrackDetail(trackId) {
  if (!trackId && trackId !== 0) {
    throw new Error('trackId is required');
  }

  return pipelineRequest(`/api/tracks/${trackId}`, {
    method: 'GET'
  });
}

/**
 * Ingest a track preview into the pipeline to ensure an audio asset exists.
 */
export async function ingestPipelineTrack(payload) {
  if (!payload?.audio_url) {
    throw new Error('audio_url is required to ingest a track');
  }

  return pipelineRequest('/api/tracks/ingest', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

/**
 * Search for a preview (YouTube by default) and kick off the full analysis chain.
 */
export async function searchAndIngestTrack(payload) {
  if (!payload?.artist || !payload?.title) {
    throw new Error('artist and title are required');
  }

  const body = {
    artist: payload.artist.trim(),
    title: payload.title.trim(),
    requested_by: payload.requested_by
  };

  if (payload.fallback_url && payload.fallback_url.trim()) {
    body.fallback_url = payload.fallback_url.trim();
  }

  return pipelineRequest('/api/tracks/search-ingest', {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

/**
 * Refresh Sonic Map data directly from the pipeline.
 */
export async function fetchPipelineSonicMap(limit = 1000) {
  const params = new URLSearchParams({ limit: String(limit) });
  return pipelineRequest(`/api/tracks/sonic-map?${params.toString()}`, {
    method: 'GET'
  });
}

/**
 * Enqueue an analysis job through the Node proxy (which forwards to the Python queue).
 */
export async function enqueueAnalysisJob(payload) {
  return apiRequest('/api/jobs/enqueue', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

/**
 * Retrieve the latest status for a given analysis job id.
 */
export async function getAnalysisJob(jobId) {
  return apiRequest(`/api/jobs/${jobId}`, {
    method: 'GET'
  });
}

/**
 * Helper describing the ordered analysis steps for a track.
 */
export const ANALYSIS_JOB_SEQUENCE = [
  { type: 'preview_fetch', label: 'Cache preview' },
  { type: 'audio_features', label: 'Audio features' },
  { type: 'embedding', label: 'Embedding vector' },
  { type: 'position', label: 'Sonic map position' }
];

export const NODE_API_BASE = DEFAULT_API_BASE;
export const PIPELINE_API_BASE = DEFAULT_PIPELINE_BASE;
