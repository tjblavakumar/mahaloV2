import { useEffect, useState } from 'react';
import Markdown from 'react-markdown';
import ProjectConfig from './components/ProjectConfig';
import ProjectSelector from './components/ProjectSelector';
import ProjectSettings from './components/ProjectSettings';
import { getPersonas, getSystemStatus, sendMessage } from './services/api';

const starterMessages = [
  {
    role: 'assistant',
    content: 'MAHALO is ready. Ask about stories, incidents, or production signals.',
    agent: 'Orchestrator',
  },
];

function App() {
  const [personas, setPersonas] = useState([]);
  const [persona, setPersona] = useState('Executive');
  const [messages, setMessages] = useState(starterMessages);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Project state
  const [projectId, setProjectId] = useState(() => localStorage.getItem('mahalo_project_id') || '');
  const [view, setView] = useState('chat'); // 'chat' | 'config' | 'settings'
  const [projectRefresh, setProjectRefresh] = useState(0);

  useEffect(() => {
    Promise.all([getPersonas(), getSystemStatus()])
      .then(([personaData, statusData]) => {
        setPersonas(personaData.personas || []);
        setStatus(statusData);
      })
      .catch(() => setError('The API is offline. Start the MAHALO services and try again.'));
  }, []);

  const handleProjectChange = (id) => {
    if (id !== projectId) {
      setProjectId(id);
      localStorage.setItem('mahalo_project_id', id);
      setConversationId(null);
      setMessages([
        {
          role: 'assistant',
          content: `Switched to project. How can I help?`,
          agent: 'Orchestrator',
        },
      ]);
    }
  };

  const handleProjectCreated = (id) => {
    setProjectId(id);
    localStorage.setItem('mahalo_project_id', id);
    setProjectRefresh((n) => n + 1);
    setConversationId(null);
    setMessages([
      {
        role: 'assistant',
        content: `New project is set up. Ask me anything about it.`,
        agent: 'Orchestrator',
      },
    ]);
    setView('chat');
  };

  const handleProjectDeleted = () => {
    localStorage.removeItem('mahalo_project_id');
    setProjectId('');
    setProjectRefresh((n) => n + 1);
    setConversationId(null);
    setMessages(starterMessages);
    setView('chat');
  };

  async function submitMessage(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;

    setError('');
    setDraft('');
    setMessages((current) => [...current, { role: 'user', content: message, persona }]);
    setBusy(true);
    try {
      const result = await sendMessage({
        persona,
        message,
        conversation_id: conversationId,
        project_id: projectId || undefined,
      });
      setConversationId(result.conversation_id);
      setMessages((current) => [
        ...current,
        { role: 'assistant', content: result.response, agent: (result.agents_used || []).join(', ') },
      ]);
    } catch (requestError) {
      setError(requestError.message || 'Unable to reach the MAHALO API.');
    } finally {
      setBusy(false);
    }
  }

  const healthyServices = status?.healthy_services ?? 0;
  const totalServices = status?.total_services ?? 0;

  // --- Config view (new project) ---
  if (view === 'config') {
    return (
      <main className="app-shell">
        <aside className="sidebar">
          <div className="brand-mark">M</div>
          <div className="brand-copy">
            <p className="eyebrow">MAHALO / 02</p>
            <h1>New Project</h1>
            <p className="muted">Configure a new project workspace.</p>
          </div>
          <div className="sidebar-footer">MAHALO / multi-project<br />API gateway :8000</div>
        </aside>
        <section className="workspace">
          <ProjectConfig
            onCancel={() => setView('chat')}
            onCreated={handleProjectCreated}
          />
        </section>
      </main>
    );
  }

  // --- Settings view (edit project) ---
  if (view === 'settings' && projectId) {
    return (
      <main className="app-shell">
        <aside className="sidebar">
          <div className="brand-mark">M</div>
          <div className="brand-copy">
            <p className="eyebrow">MAHALO / 02</p>
            <h1>Settings</h1>
            <p className="muted">Configure the selected project.</p>
          </div>
          <div className="sidebar-footer">MAHALO / multi-project<br />API gateway :8000</div>
        </aside>
        <section className="workspace">
          <ProjectSettings
            projectId={projectId}
            onCancel={() => setView('chat')}
            onDeleted={handleProjectDeleted}
            onUpdated={() => setProjectRefresh((n) => n + 1)}
          />
        </section>
      </main>
    );
  }

  // --- Chat view ---
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark">M</div>
        <div className="brand-copy">
          <p className="eyebrow">MAHALO / 02</p>
          <h1>Controls</h1>
          <p className="muted">One conversation across the delivery stack.</p>
        </div>

        <ProjectSelector
          selectedProjectId={projectId}
          onProjectChange={handleProjectChange}
          onNewProject={() => setView('config')}
          onRefresh={projectRefresh}
        />
        {projectId && (
          <button className="settings-link" onClick={() => setView('settings')} type="button">
            Project Settings
          </button>
        )}

        <section className="sidebar-section">
          <div className="section-label">Your lens</div>
          <div className="persona-list">
            {(personas.length ? personas : [{ id: 'Executive', name: 'Executive' }]).map((item) => (
              <button
                className={`persona-option ${persona === item.id ? 'selected' : ''}`}
                key={item.id}
                onClick={() => {
                  if (item.id !== persona) {
                    setPersona(item.id);
                    setConversationId(null);
                    setMessages([
                      {
                        role: 'assistant',
                        content: `Switched to ${item.name} lens. How can I help?`,
                        agent: 'Orchestrator',
                      },
                    ]);
                  }
                }}
                type="button"
              >
                <span className="persona-dot" />
                <span>{item.name}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="sidebar-section status-panel">
          <div className="section-label">System pulse</div>
          <div className="pulse-line">
            <span className={`pulse-dot ${status?.overall_status === 'healthy' ? 'online' : ''}`} />
            <strong>{status?.overall_status || 'checking'}</strong>
          </div>
          <p className="muted">{healthyServices} of {totalServices || '...'} services reporting</p>
        </section>

        <div className="sidebar-footer">MAHALO / multi-project<br />API gateway :8000</div>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Live workspace</p>
            <h2>MAHALO: End To End AI SDLC assistant</h2>
          </div>
          <div className="header-meta">
            <span className="status-chip"><span className="pulse-dot online" /> Local mode</span>
            <span className="header-date">{projectId || 'No project'}</span>
          </div>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.map((message, index) => (
            <article className={`message-row ${message.role}`} key={`${message.role}-${index}`}>
              <div className="message-avatar">{message.role === 'assistant' ? 'M' : persona.slice(0, 1)}</div>
              <div className="message-body">
                <div className="message-meta">
                  <strong>{message.role === 'assistant' ? 'MAHALO' : message.persona || persona}</strong>
                  {message.agent && <span>{message.agent}</span>}
                </div>
                <div className="message-content"><Markdown>{message.content.replace(/\n/g, '  \n')}</Markdown></div>
              </div>
            </article>
          ))}
          {busy && <div className="typing">MAHALO is tracing the request<span>.</span><span>.</span><span>.</span></div>}
        </div>

        <div className="composer-wrap">
          {error && <div className="error-banner">{error}</div>}
          <form className="composer" onSubmit={submitMessage}>
            <textarea
              aria-label="Message MAHALO"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form.requestSubmit();
                }
              }}
              placeholder={`Ask as ${persona}...`}
              rows="1"
              value={draft}
            />
            <button className="send-button" disabled={busy || !draft.trim()} type="submit">Send <span>↗</span></button>
          </form>
          <p className="composer-hint">Enter to send / Shift + Enter for a new line</p>
        </div>
      </section>
    </main>
  );
}

export default App;
