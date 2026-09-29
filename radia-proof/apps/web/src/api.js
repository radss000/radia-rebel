const apiBaseUrl = import.meta.env.VITE_API_URL || '';

async function request(path, options) {
  const response = await fetch(`${apiBaseUrl}${path}`, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || `Request failed with status ${response.status}`);
  }

  return payload;
}

export const api = {
  getHealth: () => request('/api/health'),
  getConfig: () => request('/api/config'),
  listProofs: () => request('/api/proofs'),
  createProof: ({ title, artistName, audioFile }) => {
    const body = new FormData();
    body.append('title', title);
    body.append('artistName', artistName);
    body.append('audioFile', audioFile);
    return request('/api/proofs', { method: 'POST', body });
  },
  verifyProof: (proofId, audioFile) => {
    const body = new FormData();
    body.append('audioFile', audioFile);
    return request(`/api/proofs/${proofId}/verify`, { method: 'POST', body });
  }
};
