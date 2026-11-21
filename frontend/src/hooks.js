import { useEffect, useRef, useState } from 'react';
import { knowledge } from './api';

export function useCatalog(resource, revision) {
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState({ items: [], total: 0, loading: true, error: '' });
  const [refresh, setRefresh] = useState(0);
  const latest = useRef(0);
  useEffect(() => {
    const current = ++latest.current;
    setState(s => ({ ...s, loading: true, error: '' }));
    const timer = setTimeout(() => {
      knowledge(`/${resource}?${new URLSearchParams({ query, offset, limit: 20 })}`)
        .then(data => { if (latest.current === current) setState({ ...data, loading: false, error: '' }); })
        .catch(error => { if (latest.current === current) setState(s => ({ ...s, loading: false, error: error.message })); });
    }, 220);
    return () => { clearTimeout(timer); latest.current++; };
  }, [resource, query, offset, revision, refresh]);
  return { ...state, query, offset, setQuery: value => { setQuery(value); setOffset(0); }, setOffset,
    reload: () => setRefresh(n => n + 1) };
}
