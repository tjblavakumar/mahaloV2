import { useState } from 'react';
import { createProject, generateProjectData } from '../services/api';

const DOMAINS = ['healthcare', 'fintech', 'e-commerce', 'saas', 'devops', 'other'];

/**
 * Auto-generate a project key from name.
 * Takes first letter of each word, uppercase, max 6 chars.
 * Falls back to first 4 chars for single words.
 */
function generateKey(name) {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) {
    return words
      .map((w) => w[0] || '')
      .join('')
      .toUpperCase()
      .slice(0, 6);
  }
  return name.trim().slice(0, 4).toUpperCase();
}

export default function ProjectConfig({ onCancel, onCreated }) {
  const [form, setForm] = useState({
    name: '',
    project_key: '',
    description_goal: '',
    description_users: '',
    description_purpose: '',
    domain: 'other',
    connection_mode: 'local',
    jira_url: '',
    jira_token: '',
    servicenow_url: '',
    servicenow_credentials: '',
    splunk_url: '',
    splunk_token: '',
  });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState(null); // holds created project after success
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState(null);

  const updateField = (field, value) => {
    const next = { ...form, [field]: value };
    // Auto-generate key when name changes (unless manually edited)
    if (field === 'name' && !form._keyManual) {
      next.project_key = generateKey(value);
    }
    setForm(next);
    // Clear error for that field
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: null }));
    }
  };

  const markKeyManual = () => {
    setForm((prev) => ({ ...prev, _keyManual: true }));
  };

  const validate = () => {
    const errs = {};
    if (!form.name.trim()) errs.name = 'Project name is required';
    if (!form.description_goal.trim()) errs.description_goal = 'Goal is required';
    if (!form.description_users.trim()) errs.description_users = 'Target users is required';
    if (!form.description_purpose.trim()) errs.description_purpose = 'Purpose is required';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        project_key: form.project_key || undefined,
        description_goal: form.description_goal.trim(),
        description_users: form.description_users.trim(),
        description_purpose: form.description_purpose.trim(),
        domain: form.domain,
        connection_mode: form.connection_mode,
      };
      if (form.connection_mode === 'real') {
        if (form.jira_url) payload.jira_url = form.jira_url;
        if (form.jira_token) payload.jira_token = form.jira_token;
        if (form.servicenow_url) payload.servicenow_url = form.servicenow_url;
        if (form.servicenow_credentials) payload.servicenow_credentials = form.servicenow_credentials;
        if (form.splunk_url) payload.splunk_url = form.splunk_url;
        if (form.splunk_token) payload.splunk_token = form.splunk_token;
      }
      const project = await createProject(payload);
      setCreated(project);
    } catch (err) {
      setErrors({ _form: err.message || 'Failed to create project' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleGenerate = async () => {
    if (!created) return;
    setGenerating(true);
    setGenResult(null);
    try {
      const result = await generateProjectData(created.id);
      setGenResult(result);
      if (result.success) {
        // Short delay then navigate to chat
        setTimeout(() => onCreated(created.id), 800);
      }
    } catch (err) {
      setGenResult({ success: false, error: err.message });
    } finally {
      setGenerating(false);
    }
  };

  const handleSkip = () => {
    if (created) onCreated(created.id);
  };

  // --- Success state: project created ---
  if (created) {
    return (
      <div className="config-page">
        <div className="config-card">
          <div className="config-success">
            <h2>Project Created</h2>
            <p>
              <strong>{created.name}</strong> ({created.key}) is ready.
            </p>
            <p className="muted">
              The project starts empty. Generate mock data to populate it with realistic
              domain-appropriate stories, bugs, incidents, and logs.
            </p>
            <div className="config-actions">
              <button
                className="btn-primary"
                onClick={handleGenerate}
                disabled={generating}
                type="button"
              >
                {generating ? 'Generating...' : 'Generate Mock Data'}
              </button>
              <button className="btn-secondary" onClick={handleSkip} type="button">
                Skip — Start Empty
              </button>
            </div>
            {genResult && genResult.success && (
              <p className="gen-success">
                Data generated: {genResult.counts?.stories || 0} stories,{' '}
                {genResult.counts?.bugs || 0} bugs, {genResult.counts?.logs || 0} logs
              </p>
            )}
            {genResult && !genResult.success && (
              <p className="gen-error">{genResult.error || 'Generation failed'}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // --- Form state ---
  return (
    <div className="config-page">
      <div className="config-card">
        <div className="config-header">
          <h2>New Project</h2>
          <button className="btn-text" onClick={onCancel} type="button">
            Cancel
          </button>
        </div>

        <form onSubmit={handleSubmit} className="config-form">
          {errors._form && <div className="error-banner">{errors._form}</div>}

          <div className="form-group">
            <label htmlFor="name">Project Name *</label>
            <input
              id="name"
              type="text"
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="e.g., HealthSync"
              className={errors.name ? 'input-error' : ''}
            />
            {errors.name && <span className="field-error">{errors.name}</span>}
          </div>

          <div className="form-group form-group-sm">
            <label htmlFor="project_key">Project Key</label>
            <input
              id="project_key"
              type="text"
              value={form.project_key}
              onChange={(e) => {
                markKeyManual();
                updateField('project_key', e.target.value.toUpperCase().slice(0, 6));
              }}
              placeholder="Auto-generated"
              maxLength={6}
            />
          </div>

          <div className="form-group">
            <label htmlFor="description_goal">Goal of the Project *</label>
            <textarea
              id="description_goal"
              value={form.description_goal}
              onChange={(e) => updateField('description_goal', e.target.value)}
              placeholder="What is this project trying to achieve?"
              rows={3}
              className={errors.description_goal ? 'input-error' : ''}
            />
            {errors.description_goal && <span className="field-error">{errors.description_goal}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="description_users">Target Users / Audience *</label>
            <textarea
              id="description_users"
              value={form.description_users}
              onChange={(e) => updateField('description_users', e.target.value)}
              placeholder="Who are the end users of this system?"
              rows={2}
              className={errors.description_users ? 'input-error' : ''}
            />
            {errors.description_users && <span className="field-error">{errors.description_users}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="description_purpose">Purpose / Business Context *</label>
            <textarea
              id="description_purpose"
              value={form.description_purpose}
              onChange={(e) => updateField('description_purpose', e.target.value)}
              placeholder="Why does this project exist? What problem does it solve?"
              rows={2}
              className={errors.description_purpose ? 'input-error' : ''}
            />
            {errors.description_purpose && <span className="field-error">{errors.description_purpose}</span>}
          </div>

          <div className="form-group form-group-sm">
            <label htmlFor="domain">Domain</label>
            <select id="domain" value={form.domain} onChange={(e) => updateField('domain', e.target.value)}>
              {DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Connection Mode</label>
            <div className="mode-toggle">
              <button
                type="button"
                className={`mode-btn ${form.connection_mode === 'local' ? 'active' : ''}`}
                onClick={() => updateField('connection_mode', 'local')}
              >
                Local Simulation
              </button>
              <button
                type="button"
                className={`mode-btn ${form.connection_mode === 'real' ? 'active' : ''}`}
                onClick={() => updateField('connection_mode', 'real')}
              >
                Real Services
              </button>
            </div>
          </div>

          {form.connection_mode === 'real' && (
            <fieldset className="real-fields">
              <legend>Service Credentials</legend>
              <div className="form-group form-group-sm">
                <label htmlFor="jira_url">JIRA URL</label>
                <input id="jira_url" type="url" value={form.jira_url} onChange={(e) => updateField('jira_url', e.target.value)} placeholder="https://your-org.atlassian.net" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="jira_token">JIRA API Token</label>
                <input id="jira_token" type="password" value={form.jira_token} onChange={(e) => updateField('jira_token', e.target.value)} placeholder="API token" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="servicenow_url">ServiceNow URL</label>
                <input id="servicenow_url" type="url" value={form.servicenow_url} onChange={(e) => updateField('servicenow_url', e.target.value)} placeholder="https://your-instance.service-now.com" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="servicenow_credentials">ServiceNow Credentials</label>
                <input id="servicenow_credentials" type="password" value={form.servicenow_credentials} onChange={(e) => updateField('servicenow_credentials', e.target.value)} placeholder="username:password or token" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="splunk_url">Splunk URL</label>
                <input id="splunk_url" type="url" value={form.splunk_url} onChange={(e) => updateField('splunk_url', e.target.value)} placeholder="https://splunk.your-org.com:8089" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="splunk_token">Splunk Token</label>
                <input id="splunk_token" type="password" value={form.splunk_token} onChange={(e) => updateField('splunk_token', e.target.value)} placeholder="HEC token" />
              </div>
            </fieldset>
          )}

          <div className="config-actions">
            <button className="btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Project'}
            </button>
            <button className="btn-secondary" type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
