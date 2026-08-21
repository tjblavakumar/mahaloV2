import { useEffect, useState } from 'react';
import { getProjects } from '../services/api';

/**
 * Project selector dropdown for the sidebar.
 * Stores selected project_id in localStorage and notifies parent on change.
 */
export default function ProjectSelector({ selectedProjectId, onProjectChange, onNewProject, onRefresh }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchProjects = () => {
    setLoading(true);
    getProjects()
      .then((data) => {
        setProjects(data.projects || []);
        // Auto-select first project if none selected
        if (!selectedProjectId && data.projects?.length > 0) {
          const defaultId = localStorage.getItem('mahalo_project_id') || data.projects[0].id;
          const exists = data.projects.some((p) => p.id === defaultId);
          onProjectChange(exists ? defaultId : data.projects[0].id);
        }
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchProjects();
  }, [onRefresh]);

  const handleChange = (e) => {
    const id = e.target.value;
    if (id === '__new__') {
      onNewProject();
    } else {
      onProjectChange(id);
    }
  };

  if (loading && projects.length === 0) {
    return (
      <section className="sidebar-section project-section">
        <div className="section-label">Project</div>
        <div className="muted">Loading...</div>
      </section>
    );
  }

  return (
    <section className="sidebar-section project-section">
      <div className="section-label">Project</div>
      <select
        className="project-select"
        value={selectedProjectId || ''}
        onChange={handleChange}
        aria-label="Select project"
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
        <option value="__new__">+ New Project</option>
      </select>
      {selectedProjectId && (
        <div className="project-meta">
          <span className="project-key">
            {projects.find((p) => p.id === selectedProjectId)?.key || ''}
          </span>
          <span className="project-domain">
            {projects.find((p) => p.id === selectedProjectId)?.domain || ''}
          </span>
        </div>
      )}
    </section>
  );
}
