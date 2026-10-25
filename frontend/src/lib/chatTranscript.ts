export type ChatRole = 'user' | 'assistant';

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  timestamp: string;
  // Images attached in this session (data URLs). Not saved: reloaded history
  // shows the "[n images attached]" note instead.
  images?: string[];
};

export type StoredChatMessage = { role: ChatRole; content: string; created_at?: string | null };

// SQLite stores CURRENT_TIMESTAMP as UTC "YYYY-MM-DD HH:MM:SS".
export const formatStoredTimestamp = (createdAt?: string | null): string => {
  if (!createdAt) return '';
  const parsed = new Date(`${createdAt.replace(' ', 'T')}${/[zZ]|[+-]\d\d:?\d\d$/.test(createdAt) ? '' : 'Z'}`);
  return Number.isNaN(parsed.getTime()) ? createdAt : parsed.toLocaleString();
};

export const fromStoredMessages = (stored: StoredChatMessage[]): ChatMessage[] =>
  stored
    .filter((message) => (message.role === 'user' || message.role === 'assistant') && typeof message.content === 'string')
    .map((message, index) => ({
      id: `history-${index}`,
      role: message.role,
      text: message.content,
      timestamp: formatStoredTimestamp(message.created_at),
    }));

// The whole conversation as a Markdown document, for copying or saving.
export const toMarkdownTranscript = (messages: ChatMessage[], exportedAt: Date = new Date()): string => {
  const parts = [`# Astral AI conversation`, ``, `_Exported ${exportedAt.toLocaleString()}_`, ``];
  for (const message of messages) {
    const speaker = message.role === 'user' ? 'You' : 'Astral AI';
    parts.push(`---`, ``, `**${speaker}**${message.timestamp ? ` · ${message.timestamp}` : ''}`, ``, message.text.trim(), ``);
  }
  return `${parts.join('\n').trimEnd()}\n`;
};

export const transcriptFilename = (date: Date = new Date(), extension = 'md'): string => {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `astral-chat-${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}.${extension}`;
};

export const downloadTextFile = (filename: string, text: string, type = 'text/markdown') => {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

export const copyText = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

// Puts formatted HTML and plain text on the clipboard together, so pasting into
// Word or Google Docs keeps tables and headings while plain editors get text.
// Falls back to plain text where rich clipboard writes are unavailable.
export const copyRich = async (html: string, plain: string): Promise<boolean> => {
  try {
    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([plain], { type: 'text/plain' }),
        }),
      ]);
      return true;
    }
  } catch {
    // Fall back to plain text below.
  }
  return copyText(plain);
};
