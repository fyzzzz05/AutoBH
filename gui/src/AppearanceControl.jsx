import { useEffect, useState } from 'react';
import { Desktop, Sun, Moon } from '@phosphor-icons/react';
import { applyAppearance, normalizeAppearance } from './appearance.js';

export function AppearanceControl({ save }) {
  const [mode, setMode] = useState(() => normalizeAppearance(document.documentElement.dataset.appearance));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => applyAppearance(mode, media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [mode]);
  async function change(event) {
    const next = event.target.value;
    setSaving(true); setError('');
    try { await save(next); setMode(next); }
    catch { setError('外观未保存，请重试'); }
    finally { setSaving(false); }
  }
  const Icon = mode === 'system' ? Desktop : mode === 'dark' ? Moon : Sun;
  return <div className="appearance-control">
    <label className="appearance-picker" title="外观">
      <Icon size={16} aria-hidden="true" />
      <select aria-label="外观" value={mode} onChange={change} disabled={saving}>
        <option value="system">系统</option><option value="light">浅色</option><option value="dark">深色</option>
      </select>
    </label>
    {error && <span className="appearance-error" role="alert">{error}</span>}
  </div>;
}
