import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Search from './Search';
import Knowledge from './Knowledge';
import { request } from './api';
import { Icon } from './ui';
import './styles.css';

const navigation = [{ id: 'search', icon: 'chat', title: 'Задать вопрос' }, { id: 'documents', icon: 'file', title: 'Документы' }, { id: 'wiki', icon: 'wiki', title: 'Wiki команды' }];
function App() {
  const initial = location.hash.slice(1);
  const [page, setPage] = useState(navigation.some(n => n.id === initial) ? initial : 'search');
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(null);
  const [history, setHistory] = useState([]);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState('checking');
  useEffect(() => {
    const hashChange = () => { const id = location.hash.slice(1); if (navigation.some(n => n.id === id)) setPage(id); };
    window.addEventListener('hashchange', hashChange);
    return () => window.removeEventListener('hashchange', hashChange);
  }, []);
  useEffect(() => {
    let active = true;
    async function check() {
      const health = await Promise.allSettled(['knowledge', 'search'].map(service => request(service, '/health', { signal: AbortSignal.timeout(8000) })));
      if (active) setStatus(health.every(h => h.status === 'fulfilled' && h.value.status === 'ok') ? 'online' : 'offline');
    }
    check(); const timer = setInterval(check, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  function navigate(id) { setPage(id); location.hash = id; }
  function newQuestion(question = '') { if (busy) return; setReset({ question, key: Date.now() }); navigate('search'); }
  return <div className="app-shell">
    <a className="skip-link" href="#main">К содержимому</a>
    <aside className="sidebar">
      <button className="new-question" onClick={() => newQuestion()} disabled={busy}><Icon name="plus" size={18}/> Новый вопрос</button>
      <nav aria-label="Основная навигация">{navigation.map(item => <a key={item.id} className={`nav-link ${page === item.id ? 'active' : ''}`} href={`#${item.id}`} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><Icon name={item.icon} size={19}/>{item.title}{page === item.id && <span className="nav-marker"/>}</a>)}</nav>
      {!!history.length && <div className="recent"><div className="nav-caption">НЕДАВНИЕ ВОПРОСЫ</div>{history.map(text => <button key={text} disabled={busy} onClick={() => newQuestion(text)} title={text}><Icon name="clock" size={15}/><span>{text}</span></button>)}</div>}
      <div className="sidebar-bottom"><div className="workspace"><span className="workspace-avatar">К</span><div><strong>Корпоративная база</strong><small>Локальное пространство</small></div></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div>Рабочее пространство <span>/</span> <strong>{navigation.find(n => n.id === page).title}</strong></div><div className={`connection ${status}`} title="Проверяется доступность API. Это не проверка моделей и хранилищ."><span/>{status === 'online' ? 'API доступны' : status === 'checking' ? 'Проверяем соединение' : 'Есть проблемы с API'}</div></header>
      <main id="main" tabIndex={-1}><div hidden={page !== 'search'}><Search busy={busy} setBusy={setBusy} reset={reset} onHistory={text => setHistory(h => [text, ...h.filter(t => t !== text)].slice(0, 5))}/></div><Knowledge view={page} revision={revision} onChange={() => setRevision(n => n + 1)}/></main>
      <footer className="app-footer"><span>Корпоративная база знаний</span></footer>
    </div>
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
