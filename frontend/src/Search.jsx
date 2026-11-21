import React, { useState } from 'react';
import { citationMarkdown, knowledge, originalUrl, post, request } from './api';
import { Busy, Icon, Markdown, Notice } from './ui';

function Source({ source }) {
  const [document, setDocument] = useState(null);
  const [error, setError] = useState('');
  React.useEffect(() => {
    let active = true;
    knowledge(`/documents/${source.document_id}`).then(data => { if (active) setDocument(data); })
      .catch(() => { if (active) setError('Название недоступно'); });
    return () => { active = false; };
  }, [source.document_id]);
  return <a className="source-card" id={`source-${source.source_id}`} href={originalUrl(source.document_id)}>
    <span className="source-number">{source.source_id}</span><span className="source-text"><strong>{document?.filename || `Документ №${source.document_id}`}</strong><small>{error || `Фрагмент ${Number(source.matched_position ?? 0) + 1} · Скачать оригинал`}</small></span><Icon name="download" size={16}/>
  </a>;
}

export default function Search({ busy, setBusy, reset, onHistory }) {
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState('');
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  React.useEffect(() => { if (reset) { setQuestion(reset.question || ''); if (!reset.question) { setAnswer(null); setAsked(''); setError(''); } } }, [reset]);
  async function submit(e) {
    e.preventDefault();
    if (!question.trim() || busy) return;
    const text = question.trim();
    setBusy(true); setError(''); setAnswer(null); setAsked(text); setCopied(false);
    try {
      const data = await request('search', '/questions', post({ question: text }));
      setAnswer(data); onHistory(text);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <section aria-label="Поиск по базе знаний">
    <form className="question-form" onSubmit={submit}>
      <label className="sr-only" htmlFor="question">Ваш вопрос</label>
      <textarea id="question" value={question} maxLength={10000} onChange={e => setQuestion(e.target.value)} placeholder="Что вы хотите узнать?" rows={3} disabled={busy}
        onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); e.currentTarget.form.requestSubmit(); } }}/>
      <div className="question-footer"><button className="button primary" disabled={busy || !question.trim()}>{busy ? <Busy>Ищем ответ</Busy> : <>Найти ответ <Icon name="arrow" size={18}/></>}</button></div>
    </form>
    <Notice>{error}</Notice>
    {busy && <div className="search-progress"><span className="spinner"/><div><strong>Ищем подтверждения в базе знаний</strong><p>Сопоставляем документы, изучаем Wiki и готовим ответ с источниками. Это может занять несколько минут.</p></div></div>}
    {answer && <div className="answer-layout"><article className="answer-card"><div className="answer-header"><div><span className="eyebrow">ОТВЕТ</span><h2>{asked}</h2></div><button className="icon-button" title={copied ? 'Ответ скопирован' : 'Скопировать ответ'} aria-label="Скопировать ответ" onClick={async () => { try { await navigator.clipboard.writeText(answer.answer); setCopied(true); } catch { setError('Не удалось скопировать ответ. Выделите и скопируйте текст вручную.'); } }}><Icon name={copied ? 'check' : 'copy'}/></button></div>
      {answer.explore_status === 'interrupted' && <Notice kind="warning">Обход Wiki прерван. Ответ подготовлен по уже найденным материалам; охват может быть неполным.</Notice>}
      <Markdown>{citationMarkdown(answer.answer, answer.sources)}</Markdown>
      {!!answer.missing_parts?.length && <Notice kind="warning">Не найдено подтверждений: {answer.missing_parts.join('; ')}.</Notice>}
      {!!answer.budget_missing_parts?.length && <Notice kind="warning">Часть материалов не вошла в объём ответа: {answer.budget_missing_parts.join('; ')}.</Notice>}
      <div className="answer-disclaimer"><Icon name="info" size={16}/> Проверьте важные решения по оригиналам документов.</div>
    </article><aside className="sources"><h3>Источники <span className="count">{answer.sources.length}</span></h3><p>Номера соответствуют ссылкам в ответе.</p>{answer.sources.map(source => <Source key={source.source_id} source={source}/>)}{!answer.sources.length && <p className="muted">Подтверждающие источники не найдены.</p>}</aside></div>}
  </section>;
}
