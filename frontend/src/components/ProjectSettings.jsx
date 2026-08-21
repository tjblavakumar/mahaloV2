import { useEffect, useState } from 'react';
import { deleteProject, generateProjectData, getProject, updateProject } from '../services/api';

const DOMAINS = ['healthcare', 'fintech', 'e-commerce', 'saas', 'devops', 'other'];

/**
 * Project settings/edit view. Allows updating description, domain,
 * connection mode, generating more data, or deleting the project.
 */
export default function ProjectSettings({ projectId, onCancel, onDeleted, onUpdated }) {
  const [project, setProject] = useState(null);
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setLoading(true);
    getProject(projectId)
      .then((data) => {
        setProject(data);
        setForm({
          description_goal: data.description_goal || '',
          description_users: data.description_users || '',
          description_purpose: data.description_purpose || '',
          domain: data.domain || 'other',
          connection_mode: data.connection_mode || 'local',
          jira_url: data.jira_url || '',
          jira_token: data.jira_token || '',
          servicenow_url: data.servicenow_url || '',
          servicenow_credentials: data.servicenow_credentials || '',
          splunk_url: data.splunk_url || '',
          splunk_token: data.splunk_token || '',
        });
      })
      .catch((err) => setError(err.message || 'Failed to load project'))
      .finally(() => setLoading(false));
  }, [projectId]);

  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {};
      // Only send changed fields
      for (const [key, value] of Object.entries(form)) {
        if (project[key] !== value) {
          payload[key] = value;
        }
      }
      if (Object.keys(payload).length === 0) {
        setSaved(true);
        setSaving(false);
        return;
      }
      const updated = await updateProject(projectId, payload);
      setProject(updated);
      setSaved(true);
      if (onUpdated) onUpdated();
    } catch (err) {
      setError(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setGenResult(null);
    try {
      const result = await generateProjectData(projectId);
      setGenResult(result);
    } catch (err) {
      setGenResult({ success: false, error: err.message });
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async () => {
    try {
      await deleteProject(projectId);
      onDeleted();
    } catch (err) {
      setError(err.message || 'Failed to delete project');
    }
  };

  if (loading) {
    return (
      <div className="config-page">
        <div className="config-card"><p className="muted">Loading project...</p></div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="config-page">
        <div className="config-card">
          <p className="gen-error">{error || 'Project not found'}</p>
          <button className="btn-secondary" onClick={onCancel} type="button">Back</button>
        </div>
      </div>
    );
  }

  return (
    <div className="config-page">
      <div className="config-card">
        <div className="config-header">
          <div>
            <h2>Project Settings</h2>
            <p className="muted">{project.name} <span className="project-key">{project.key}</span></p>
          </div>
          <button className="btn-text" onClick={onCancel} type="button">Back to Chat</button>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <div className="config-form">
          <div className="form-group">
            <label htmlFor="s_goal">Goal of the Project</label>
            <textarea
              id="s_goal"
              value={form.description_goal}
              onChange={(e) => updateField('description_goal', e.target.value)}
              rows={3}
            />
          </div>

          <div className="form-group">
            <label htmlFor="s_users">Target Users / Audience</label>
            <textarea
              id="s_users"
              value={form.description_users}
              onChange={(e) => updateField('description_users', e.target.value)}
              rows={2}
            />
          </div>

          <div className="form-group">
            <label htmlFor="s_purpose">Purpose / Business Context</label>
            <textarea
              id="s_purpose"
              value={form.description_purpose}
              onChange={(e) => updateField('description_purpose', e.target.value)}
              rows={2}
            />
          </div>

          <div className="form-group form-group-sm">
            <label htmlFor="s_domain">Domain</label>
            <select id="s_domain" value={form.domain} onChange={(e) => updateField('domain', e.target.value)}>
              {DOMAINS.map((d) => (
                <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
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
              >Local Simulation</button>
              <button
                type="button"
                className={`mode-btn ${form.connection_mode === 'real' ? 'active' : ''}`}
                onClick={() => updateField('connection_mode', 'real')}
              >Real Services</button>
            </div>
          </div>

          {form.connection_mode === 'real' && (
            <fieldset className="real-fields">
              <legend>Service Credentials</legend>
              <div className="form-group form-group-sm">
                <label htmlFor="s_jira_url">JIRA URL</label>
                <input id="s_jira_url" type="url" value={form.jira_url} onChange={(e) => updateField('jira_url', e.target.value)} placeholder="https://your-org.atlassian.net" />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="s_jira_token">JIRA API Token</label>
                <input id="s_jira_token" type="password" value={form.jira_token} onChange={(e) => updateField('jira_token', e.target.value)} />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="s_sn_url">ServiceNow URL</label>
                <input id="s_sn_url" type="url" value={form.servicenow_url} onChange={(e) => updateField('servicenow_url', e.target.value)} />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="s_sn_cred">ServiceNow Credentials</label>
                <input id="s_sn_cred" type="password" value={form.servicenow_credentials} onChange={(e) => updateField('servicenow_credentials', e.target.value)} />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="s_splunk_url">Splunk URL</label>
                <input id="s_splunk_url" type="url" value={form.splunk_url} onChange={(e) => updateField('splunk_url', e.target.value)} />
              </div>
              <div className="form-group form-group-sm">
                <label htmlFor="s_splunk_token">Splunk Token</label>
                <input id="s_splunk_token" type="password" value={form.splunk_token} onChange={(e) => updateField('splunk_token', e.target.value)} />
              </div>
            </fieldset>
          )}

          <div className="config-actions">
            <button className="btn-primary" onClick={handleSave} disabled={saving} type="button">
              {saving ? 'Saving...' : saved ? 'Saved' : 'Save Changes'}
            </button>
          </div>
        </div>

        {/* Data Management Section */}
        <div className="settings-section">
          <div className="section-label">Data Management</div>
          <p className="muted">
            {project.data_generated
              ? 'This project has generated data. You can generate more or regenerate.'
              : 'This project has no generated data yet.'}
          </p>
          <div className="config-actions">
            <button className="btn-primary" onClick={handleGenerate} disabled={generating} type="button">
              {generating ? 'Generating...' : project.data_generated ? 'Generate More Data' : 'Generate Mock Data'}
            </button>
          </div>
          {genResult && genResult.success && (
            <p className="gen-success">
              Generated: {genResult.counts?.users || 0} users, {genResult.counts?.stories || 0} stories,{' '}
              {genResult.counts?.bugs || 0} bugs, {genResult.counts?.incidents || 0} incidents,{' '}
              {genResult.counts?.logs || 0} logs
            </p>
          )}
          {genResult && !genResult.success && (
            <p className="gen-error">{genResult.error || 'Generation failed'}</p>
          )}
        </div>

        {/* Danger Zone */}
        <div className="settings-section danger-zone">
          <div className="section-label">Danger Zone</div>
          {!confirmDelete ? (
            <button className="btn-danger" onClick={() => setConfirmDelete(true)} type="button">
              Delete Project
            </button>
          ) : (
            <div className="confirm-delete">
              <p className="gen-error">This will permanently delete the project, its database, and all data.</p>
              <div className="config-actions">
                <button className="btn-danger" onClick={handleDelete} type="button">
                  Yes, Delete Forever
                </button>
                <button className="btn-secondary" onClick={() => setConfirmDelete(false)} type="button">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
