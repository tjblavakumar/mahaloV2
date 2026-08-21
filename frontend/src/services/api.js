const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return response.json();
}

export function getPersonas() {
  return request('/api/chat/personas');
}

export function sendMessage(payload) {
  return request('/api/chat/message', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSystemStatus() {
  return request('/api/admin/status');
}

export function resetDemoData(projectId) {
  const query = projectId ? `?project_id=${projectId}` : '';
  return request(`/api/admin/reset-data${query}`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Project APIs
// ---------------------------------------------------------------------------

export function getProjects() {
  return request('/api/projects');
}

export function getProject(id) {
  return request(`/api/projects/${id}`);
}

export function createProject(payload) {
  return request('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteProject(id) {
  return request(`/api/projects/${id}`, { method: 'DELETE' });
}

export function updateProject(id, payload) {
  return request(`/api/projects/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function generateProjectData(id) {
  return request(`/api/projects/${id}/generate-data`, { method: 'POST' });
}

export function resetProjectData(id) {
  return request(`/api/projects/${id}/reset-data`, { method: 'POST' });
}
