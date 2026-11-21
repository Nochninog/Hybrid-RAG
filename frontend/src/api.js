export class ApiError extends Error {
  constructor(message, detail = {}, status = 0) {
    super(message);
    this.detail = detail;
    this.status = status;
  }
}

export async function request(service, path, options = {}) {
  let response;
  try {
    response = await fetch(`/api/${service}${path}`, options);
  } catch {
    throw new ApiError('Не удалось получить ответ сервера. Проверьте соединение. Если операция изменяла данные, проверьте её результат перед повтором.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    throw new ApiError(message || (response.status === 413 ? 'Файл слишком большой. Максимум — 20 МБ.' : 'Сервис не завершил операцию. Проверьте результат перед повтором.'),
      detail && !Array.isArray(detail) && typeof detail === 'object' ? detail : {}, response.status);
  }
  if (data === null) throw new ApiError('Сервер вернул неожиданный ответ. Проверьте результат операции перед повтором.');
  return data;
}

export const knowledge = (path, options) => request('knowledge', path, options);
export const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export const originalUrl = id => `/api/knowledge/documents/${Number(id)}/original`;

export function validateFile(file) {
  if (!file) return 'Выберите документ.';
  if (!/\.(md|txt|pdf)$/i.test(file.name)) return 'Выберите PDF, Markdown (.md) или текстовый файл (.txt).';
  if (file.size === 0) return 'Файл пустой. Выберите документ с содержимым.';
  if (file.size > 20 * 1024 * 1024) return 'Размер файла превышает 20 МБ.';
  return '';
}

export function formatSize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} МБ` : `${Math.max(1, Math.ceil(bytes / 1024))} КБ`;
}

export function citationMarkdown(text, sources) {
  const ids = new Set(sources.map(s => String(s.source_id)));
  // Номера ссылаются только на источники текущего ответа.
  return text.replace(/\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g, (match, group) =>
    group.split(',').map(s => s.trim()).every(id => ids.has(id))
      ? group.split(',').map(s => s.trim()).map(id => `[${id}](#source-${id})`).join(' ')
      : match);
}
