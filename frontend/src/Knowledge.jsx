import React, { useRef, useState } from 'react';
import { formatSize, knowledge, originalUrl, post, validateFile } from './api';
import { useCatalog } from './hooks';
import { Busy, Empty, Icon, Markdown, Modal, Notice, Pagination } from './ui';

function WikiReader({ id, close, onChange }) {
  const [page, setPage] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  React.useEffect(() => {
    let active = true;
    knowledge(`/wiki-pages/${id}`).then(data => { if (active) setPage(data); })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [id]);
  async function action(type) {
    if (busy) return;
    setBusy(type); setError(''); setMessage('');
    try {
      const result = await knowledge(`/wiki-pages/${id}/${type}`, { method: 'POST' });
      setMessage(type === 'links' ? `Связи сохранены: ${result.saved_links}.` : 'Индекс Wiki обновлён.'); onChange();
    } catch (err) { setError(err.detail.saved_links != null ? `${err.message} Уже сохранено связей: ${err.detail.saved_links}.` : err.message); }
    finally { setBusy(''); }
  }
  return <Modal title={page?.title || 'Wiki-страница'} close={() => { if (!busy) close(); }}>
    <Notice>{error}</Notice><Notice kind="success">{message}</Notice>
    {!page && !error && <Busy>Загружаем страницу…</Busy>}
    {page && <><div className="reader-meta"><span>WIKI / {id}</span><span>Документы-источники: {page.document_ids.map((id, i) => <React.Fragment key={id}>{i > 0 && ', '}<a href={originalUrl(id)}>№{id}</a></React.Fragment>)}</span></div><Markdown>{page.content}</Markdown><div className="modal-actions"><button className="button secondary" disabled={!!busy} onClick={() => action('index')}><Icon name="refresh" size={17}/> Обновить индекс</button><button className="button primary" disabled={!!busy} onClick={() => action('links')}><Icon name="link" size={17}/> Построить связи</button></div><p className="fine-print">Построение связей вызывает модель и сохраняет найденные переходы между Wiki.</p></>}
    {busy && <Busy>Выполняем операцию… Это может занять несколько минут.</Busy>}
  </Modal>;
}

export default function Knowledge({ view, revision, onChange }) {
  const docs = useCatalog('documents', revision);
  const wiki = useCatalog('wiki-pages', revision);
  const inputRef = useRef(null);
  const [selected, setSelected] = useState({});
  const [file, setFile] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [job, setJob] = useState('');
  const [uploadError, setUploadError] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [rowError, setRowError] = useState('');
  const [creating, setCreating] = useState(false);
  const [topic, setTopic] = useState('');
  const [wikiError, setWikiError] = useState(null);
  const [wikiMessage, setWikiMessage] = useState('');
  const [preview, setPreview] = useState(null);
  const catalog = view === 'wiki' ? wiki : docs;
  const isWiki = view === 'wiki';
  const selectedDocs = Object.values(selected);
  const busy = !!job;

  function chooseFile(value) {
    if (busy) return;
    setFile(value); setUploadError(null); setUploadMessage('');
    const error = validateFile(value);
    if (error) setUploadError({ message: error, detail: {} });
  }
  async function upload(e) {
    e.preventDefault();
    const error = validateFile(file);
    if (error) { setUploadError({ message: error, detail: {} }); return; }
    if (busy) return;
    setJob('upload'); setUploadError(null); setUploadMessage('');
    const form = new FormData(); form.append('file', file);
    try {
      const result = await knowledge('/documents', { method: 'POST', body: form });
      setUploadMessage(`«${result.filename}» добавлен в поиск. Документ №${result.document_id}.`);
      setSelected(s => ({ ...s, [result.document_id]: { id: result.document_id, filename: result.filename } }));
      setFile(null); if (inputRef.current) inputRef.current.value = ''; onChange();
    } catch (err) { setUploadError(err); onChange(); }
    finally { setJob(''); }
  }
  async function reindex(id, fromUpload = false) {
    if (busy) return;
    setJob(`doc-${id}`); setRowError('');
    try {
      await knowledge(`/documents/${id}/index`, { method: 'POST' });
      if (fromUpload) { setUploadError(null); setUploadMessage(`Документ №${id} проиндексирован.`); setFile(null); }
      onChange();
    } catch (err) { if (fromUpload) setUploadError(err); else setRowError(err.message); }
    finally { setJob(''); }
  }
  function openCreate() { setCreating(true); setWikiError(null); setWikiMessage(''); setTopic(''); }
  async function createWiki(e) {
    e.preventDefault(); if (busy || !topic.trim() || !selectedDocs.length || wikiError?.detail?.wiki_page_id) return;
    setJob('wiki'); setWikiError(null); setWikiMessage('');
    try {
      const result = await knowledge('/wiki-pages', post({ document_ids: selectedDocs.map(d => d.id), topic: topic.trim() }));
      setCreating(false); setSelected({}); setPreview(result.wiki_page_id); onChange();
    } catch (err) { setWikiError(err); onChange(); }
    finally { setJob(''); }
  }
  async function retryWiki() {
    if (busy) return;
    const id = wikiError.detail.wiki_page_id; setJob('wiki');
    try { await knowledge(`/wiki-pages/${id}/index`, { method: 'POST' }); setWikiError(null); setCreating(false); setSelected({}); setPreview(id); onChange(); }
    catch (err) { setWikiError(err); }
    finally { setJob(''); }
  }
  return <section hidden={view === 'search'} aria-labelledby="catalog-title">
    <div className="page-heading"><div><div className="eyebrow">БАЗА ЗНАНИЙ</div><h1 id="catalog-title">{isWiki ? 'Wiki команды' : 'Документы'}</h1></div>
      {isWiki ? <button className="button primary" onClick={openCreate} disabled={busy}><Icon name="plus" size={18}/> Создать Wiki</button> : <button className="button primary" onClick={() => setUploadOpen(v => !v)}><Icon name="upload" size={18}/> Добавить документ</button>}
    </div>
    {!isWiki && uploadOpen && <form className="upload-panel" onSubmit={upload}>
      <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); chooseFile(e.dataTransfer.files[0]); }}>
        <span className="upload-symbol"><Icon name="upload" size={25}/></span><div><strong>{file ? file.name : 'Перетащите документ сюда'}</strong><p>PDF, TXT или Markdown · до 20 МБ</p></div><label className={`button secondary ${busy ? 'disabled' : ''}`}>Выбрать файл<input ref={inputRef} className="file-input" type="file" accept=".pdf,.md,.txt" disabled={busy} onChange={e => chooseFile(e.target.files[0])}/></label>
      </div>
      <Notice>{uploadError?.message}{uploadError?.detail?.document_id && <><br/>Оригинал сохранён под №{uploadError.detail.document_id}. Повторите индексацию без загрузки.<button type="button" className="text-button" disabled={busy} onClick={() => reindex(uploadError.detail.document_id, true)}>Повторить индексацию</button></>}</Notice>
      <Notice kind="success">{uploadMessage}</Notice>
      <div className="upload-footer"><span className="fine-print">Документ с тем же именем заменит прежний оригинал.</span><button className="button primary" disabled={busy || !file || !!validateFile(file) || !!uploadError?.detail?.document_id}>{job === 'upload' || job.startsWith('doc-') ? <Busy>Обрабатываем документ</Busy> : 'Загрузить и обработать'}</button></div>
    </form>}
    <div className="catalog-card">
      <div className="catalog-toolbar"><label className="catalog-search"><Icon name="search" size={18}/><input aria-label={isWiki ? 'Поиск Wiki' : 'Поиск документов'} placeholder={isWiki ? 'Найти страницу по названию' : 'Найти документ по названию'} value={catalog.query} onChange={e => catalog.setQuery(e.target.value)}/></label><div className="toolbar-right"><span className="catalog-total">Всего: {catalog.total}</span><button className="icon-button" aria-label="Обновить список" onClick={catalog.reload} disabled={catalog.loading}><Icon name="refresh" size={18}/></button></div></div>
      {!isWiki && selectedDocs.length > 0 && <div className="selection-bar"><span>Выбрано документов: <strong>{selectedDocs.length}</strong></span><button className="text-button" onClick={openCreate} disabled={busy}>Создать Wiki <Icon name="arrow" size={16}/></button><button className="text-button muted" onClick={() => setSelected({})} disabled={busy}>Снять выбор</button></div>}
      <Notice>{catalog.error || rowError}</Notice>
      {catalog.loading ? <div className="catalog-loading"><Busy>Загружаем {isWiki ? 'Wiki' : 'документы'}…</Busy></div> : !catalog.error && !catalog.items.length ? <Empty icon={isWiki ? 'wiki' : 'file'} title={catalog.query ? 'Ничего не найдено' : isWiki ? 'Здесь будут знания команды' : 'Добавьте первый документ'}>{catalog.query ? 'Попробуйте другое название.' : isWiki ? 'Выберите документы и создайте Wiki по нужной теме.' : 'Загрузите PDF, Markdown или текстовый файл, чтобы искать по нему ответы.'}</Empty> : !catalog.error && <div className="table-wrap"><table><thead><tr>{!isWiki && <th className="checkbox-cell"><span className="sr-only">Выбор</span></th>}<th>{isWiki ? 'Страница' : 'Название документа'}</th><th>{isWiki ? 'Источники' : 'Размер'}</th><th>{isWiki ? 'Связи' : 'Состояние'}</th><th><span className="sr-only">Действия</span></th></tr></thead><tbody>{catalog.items.map(item => <tr key={item.id}>
        {!isWiki && <td className="checkbox-cell"><input type="checkbox" aria-label={`Выбрать ${item.filename}`} disabled={busy || !item.indexed} checked={!!selected[item.id]} onChange={e => setSelected(s => { const next = { ...s }; if (e.target.checked) next[item.id] = item; else delete next[item.id]; return next; })}/></td>}
        <td><div className="file-name"><span className={`file-symbol ${isWiki ? 'wiki-symbol' : ''}`}><Icon name={isWiki ? 'wiki' : 'file'} size={20}/></span><div>{isWiki ? <button className="title-button" onClick={() => setPreview(item.id)}>{item.title}</button> : <a className="title-button" href={originalUrl(item.id)}>{item.filename}</a>}<small>{isWiki ? `WIKI / ${item.id}` : `${item.filename.split('.').pop().toUpperCase()} · №${item.id}${item.wiki_page_ids.length ? ` · Wiki: ${item.wiki_page_ids.length}` : ''}`}</small></div></div></td>
        <td className="nowrap">{isWiki ? `${item.document_ids.length} док.` : formatSize(item.size_bytes)}</td><td>{isWiki ? <span className="muted">{item.link_count} переходов</span> : <span className={`badge ${item.indexed ? 'ready' : 'pending'}`}><span/>{item.indexed ? 'В поиске' : 'Нет индекса'}</span>}</td>
        <td>{isWiki ? <button className="icon-button" onClick={() => setPreview(item.id)} aria-label={`Открыть ${item.title}`}><Icon name="arrow" size={18}/></button> : item.indexed ? <a className="icon-button" href={originalUrl(item.id)} aria-label={`Скачать ${item.filename}`}><Icon name="download" size={18}/></a> : <button className="button secondary small" disabled={busy} onClick={() => reindex(item.id)}>{job === `doc-${item.id}` ? <Busy/> : 'Индексировать'}</button>}</td>
      </tr>)}</tbody></table></div>}
      {!catalog.loading && !catalog.error && <Pagination offset={catalog.offset} total={catalog.total} limit={20} change={catalog.setOffset}/>}
    </div>
    <div className="catalog-note"><Icon name="info" size={17}/>{isWiki ? 'Wiki — производное представление. При проверке фактов опирайтесь на оригиналы.' : 'Выберите документы в списке, чтобы собрать из них Wiki по общей теме.'}</div>
    {creating && <Modal title="Создать Wiki" close={() => { if (!busy) setCreating(false); }}><form onSubmit={createWiki}>
      <p className="modal-intro">Укажите тему. Страница будет создана по выбранным документам и добавлена в поиск.</p>
      <label className="field-label" htmlFor="wiki-topic">Тема страницы</label><input id="wiki-topic" className="text-input" placeholder="Например, порядок согласования заявок" maxLength={500} required value={topic} disabled={busy || !!wikiError?.detail?.wiki_page_id} onChange={e => setTopic(e.target.value)}/>
      <div className="field-label">Документы-источники <span className="count">{selectedDocs.length}</span></div>
      {!selectedDocs.length ? <Notice kind="warning">Сначала выберите проиндексированные документы в разделе «Документы».</Notice> : <div className="selected-documents">{selectedDocs.map(d => <div key={d.id}><Icon name="file" size={17}/><span>{d.filename}</span><button type="button" className="icon-button" aria-label={`Убрать ${d.filename}`} disabled={busy || !!wikiError?.detail?.wiki_page_id} onClick={() => setSelected(s => { const next = { ...s }; delete next[d.id]; return next; })}><Icon name="close" size={15}/></button></div>)}</div>}
      <Notice>{wikiError?.message}{wikiError?.detail?.wiki_page_id && <><br/>Страница №{wikiError.detail.wiki_page_id} сохранена. Повторите только индексацию.<button type="button" className="text-button" disabled={busy} onClick={retryWiki}>Повторить индексацию Wiki</button></>}</Notice><Notice kind="success">{wikiMessage}</Notice>
      <div className="modal-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setCreating(false)}>Закрыть</button><button className="button primary" disabled={busy || !selectedDocs.length || selectedDocs.length > 100 || !topic.trim() || !!wikiError?.detail?.wiki_page_id}>{job === 'wiki' ? <Busy>Создаём Wiki</Busy> : <>Создать страницу <Icon name="arrow" size={17}/></>}</button></div>
      <p className="fine-print">Генерация может занять несколько минут. Повторное создание добавляет новую страницу.</p>
    </form></Modal>}
    {preview && <WikiReader id={preview} close={() => setPreview(null)} onChange={onChange}/>}
  </section>;
}
