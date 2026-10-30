import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from './chatTranscript';

// Turns chat messages into plain, document-friendly HTML for pasting into Word
// or Google Docs, and for saving as a Word-compatible file. Styling is inline
// or attribute-based because word processors ignore the app's CSS classes.
// Raw HTML inside a message is never rendered (react-markdown default) and all
// text is escaped by React.

const documentComponents: Components = {
  table: ({ children }) => (
    <table border={1} cellPadding={5} cellSpacing={0} style={{ borderCollapse: 'collapse' }}>{children}</table>
  ),
  pre: ({ children }) => (
    <pre style={{ fontFamily: 'Consolas, monospace', background: '#f4f4f4', padding: '6px' }}>{children}</pre>
  ),
};

export const markdownToHtml = (markdown: string): string =>
  renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={documentComponents}>{markdown}</ReactMarkdown>,
  );

const plainTextToHtml = (text: string): string =>
  renderToStaticMarkup(
    <>{text.split(/\n{2,}/).map((paragraph, index) => (
      <p key={index}>{paragraph.split('\n').flatMap((line, i) => (i === 0 ? [line] : [<br key={i} />, line]))}</p>
    ))}</>,
  );

// AI replies are Markdown; the user's own messages are plain text.
export const messageToHtml = (message: ChatMessage): string =>
  message.role === 'assistant' ? markdownToHtml(message.text) : plainTextToHtml(message.text);

export const transcriptToHtml = (messages: ChatMessage[], exportedAt: Date = new Date()): string => {
  const header = renderToStaticMarkup(
    <>
      <h1>Astral AI conversation</h1>
      <p><em>Exported {exportedAt.toLocaleString()}</em></p>
    </>,
  );
  const body = messages.map((message) => {
    const speaker = renderToStaticMarkup(
      <p><strong>{message.role === 'user' ? 'You' : 'Astral AI'}</strong>{message.timestamp ? ` · ${message.timestamp}` : ''}</p>,
    );
    return `<hr />${speaker}${messageToHtml(message)}`;
  });
  return header + body.join('');
};

// A complete HTML document in the format Word opens directly (saved as .doc).
export const wordDocument = (bodyHtml: string, title = 'Astral AI conversation'): string => `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8" />
<title>${renderToStaticMarkup(<>{title}</>)}</title>
<style>
body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; }
table { border-collapse: collapse; }
th, td { border: 1px solid #999999; padding: 4px 6px; vertical-align: top; }
th { background: #eeeeee; }
pre, code { font-family: Consolas, monospace; font-size: 10pt; }
</style>
</head>
<body>
${bodyHtml}
</body>
</html>
`;
