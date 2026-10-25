import { useRef, useState, type ComponentPropsWithoutRef, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { copyRich, copyText, type ChatMessage as ChatMessageData } from '../lib/chatTranscript';

const useCopied = () => {
  const [copied, setCopied] = useState(false);
  const copy = async (write: () => Promise<boolean>) => {
    if (await write()) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_500);
    }
  };
  return { copied, copy };
};

function CodeBlock({ children, ...props }: ComponentPropsWithoutRef<'pre'>) {
  const preRef = useRef<HTMLPreElement>(null);
  const { copied, copy } = useCopied();
  return (
    <div className="relative group/code my-2">
      <button
        type="button"
        onClick={() => void copy(() => copyText(preRef.current?.textContent ?? ''))}
        className="absolute top-1.5 right-1.5 text-[10px] px-2 py-0.5 rounded bg-[#2a2a35] text-gray-300 hover:text-white hover:bg-[#3a3a48]"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre ref={preRef} {...props} className="overflow-x-auto rounded-lg bg-[#0a0a0c] border border-[#2a2a35] p-3 pt-7 text-xs leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

// Styled Markdown elements. Raw HTML in replies is not rendered (react-markdown
// default), so model output cannot inject markup or scripts.
const markdownComponents: Components = {
  h1: ({ children }) => <h3 className="text-base font-bold text-white mt-3 mb-1.5">{children}</h3>,
  h2: ({ children }) => <h4 className="text-sm font-bold text-white mt-3 mb-1.5">{children}</h4>,
  h3: ({ children }) => <h5 className="text-sm font-semibold text-gray-100 mt-2 mb-1">{children}</h5>,
  p: ({ children }) => <p className="my-1.5">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-1.5 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-[#a55eea] pl-3 my-2 text-gray-400">{children}</blockquote>,
  hr: () => <hr className="my-3 border-[#2a2a35]" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer noopener" className="text-[#a55eea] underline">{children}</a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-[#2a2a35]">
      <table className="min-w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="text-left font-semibold text-gray-100 bg-[#14141b] px-2 py-1.5 border-b border-[#2a2a35]">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1.5 border-b border-[#2a2a35] align-top">{children}</td>,
  pre: CodeBlock,
  code: ({ className, children }) => (
    className
      ? <code className={className}>{children}</code>
      : <code className="px-1 py-0.5 rounded bg-[#0a0a0c] border border-[#2a2a35] text-[0.85em] text-pink-300">{children}</code>
  ),
};

export function MarkdownText({ children }: { children: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{children}</ReactMarkdown>;
}

export default function ChatMessage({ message, footer }: { message: ChatMessageData; footer?: ReactNode }) {
  const { copied, copy } = useCopied();
  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`} data-testid="chat-message" data-role={message.role}>
      <div className={`group max-w-[90%] min-w-0 rounded-xl px-3 py-2 text-sm leading-relaxed shadow-md ${
        isUser
          ? 'bg-[#a55eea] text-white rounded-br-sm'
          : 'bg-[#1c1c26] text-gray-200 border border-[#2a2a35] rounded-bl-sm'
      }`}>
        {!isUser && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <div className="w-3.5 h-3.5 rounded-full bg-[#a55eea] flex items-center justify-center">
              <span className="text-[7px] text-white font-bold">A</span>
            </div>
            <span className="text-[10px] text-[#a55eea] font-semibold">Astral AI</span>
          </div>
        )}
        {isUser
          ? <span className="whitespace-pre-wrap break-words">{message.text}</span>
          : <div className="break-words"><MarkdownText>{message.text}</MarkdownText></div>}
        <div className={`flex items-center gap-2 text-[9px] mt-1 ${isUser ? 'text-purple-200' : 'text-gray-500'}`}>
          <span>{message.timestamp}</span>
          <button
            type="button"
            // Formatted for Word/Docs, with plain text for plain editors.
            onClick={() => void copy(async () => {
              // Loaded on demand: the HTML converter is only needed when copying.
              const { messageToHtml } = await import('../lib/chatDocument');
              return copyRich(messageToHtml(message), message.text);
            })}
            aria-label="Copy message"
            className="opacity-60 hover:opacity-100 underline-offset-2 hover:underline"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
          {footer}
        </div>
      </div>
    </div>
  );
}
