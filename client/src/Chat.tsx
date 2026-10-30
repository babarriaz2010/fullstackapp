import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import './App.css';
import './Chat.css';

interface LibraryDocument {
  id: string;
  filename: string;
  needs_reprocessing?: boolean;
  chunk_count?: number;
  metadata: { chunk_count?: number; status?: string };
}

interface Source {
  citation: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  chunk_index: number;
  excerpt: string;
  score: number;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
}

const suggestions = ['Summarize the main points', 'What are the key requirements?', 'What dates or deadlines are mentioned?'];

function Chat() {
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [libraryError, setLibraryError] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/documents', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load your documents. Check the backend connection and try again.');
        const body = await response.json();
        const ready = (body.documents as LibraryDocument[]).filter((document) => !document.needs_reprocessing && (document.chunk_count ?? document.metadata.chunk_count ?? 0) > 0);
        setDocuments(ready);
        const requested = new URLSearchParams(window.location.search).get('document');
        if (ready.some((document) => document.id === requested)) setDocumentId(requested!);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setLibraryError(err instanceof Error ? err.message : 'Could not load documents.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); requestRef.current?.abort(); };
  }, []);

  useEffect(() => {
    if (messages.length > 0 || sending) bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'nearest' });
  }, [messages, sending]);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question || sending || loading || documents.length === 0) return;
    const controller = new AbortController();
    requestRef.current = controller;
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: question };
    const history = messages.slice(-8).map((message) => ({ role: message.role, content: message.content.slice(0, 2000) }));
    setMessages((previous) => [...previous, userMessage]);
    setInput('');
    setSending(true);
    setError('');
    try {
      const response = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ message: question, history, document_id: documentId || null }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not get an answer. Please try again.');
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: body.answer, sources: body.sources }]);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Chat is unavailable. Please try again.');
        setMessages((previous) => previous.filter((message) => message.id !== userMessage.id));
        setInput(question);
      }
    } finally {
      if (!controller.signal.aborted) {
        setSending(false);
        requestRef.current = null;
        inputRef.current?.focus();
      }
    }
  }

  function resetConversation(nextDocumentId = documentId) {
    if (sending) return;
    setDocumentId(nextDocumentId);
    setMessages([]);
    setInput('');
    setError('');
    inputRef.current?.focus();
  }

  function renderAnswer(message: Message) {
    return message.content.split(/(\[\d+\])/g).map((part, index) => {
      const match = /^\[(\d+)\]$/.exec(part);
      const source = match && message.sources?.find((item) => item.citation === Number(match[1]));
      if (!source) return part;
      const id = `source-${message.id}-${source.citation}`;
      return <a key={index} className="inline-citation" href={`#${id}`} aria-label={`Read source ${source.citation}: ${source.filename}`}
        onClick={() => { const details = window.document.getElementById(id) as HTMLDetailsElement | null; if (details) details.open = true; }}>{part}</a>;
    });
  }

  return (
    <main className="workspace chat-workspace">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Knowledge library home"><span className="brand-mark">K</span> Knowledge library</a>
        <nav className="chat-navigation" aria-label="Main navigation"><a href="/">Documents</a><a className="active" href="/chat" aria-current="page">Chat</a></nav>
      </header>
      <section className="chat-intro">
        <p className="eyebrow">A CONVERSATION WITH YOUR KNOWLEDGE</p>
        <h1>Ask your documents.</h1>
        <p className="intro-copy">Find the answers in your files, with the passages to back them up.</p>
      </section>
      <section className="chat-panel" aria-label="Document chat">
        <div className="chat-toolbar">
          <div className="document-selector"><label htmlFor="chat-document">Search in</label><select id="chat-document" value={documentId} disabled={sending || loading || documents.length === 0} onChange={(event) => resetConversation(event.target.value)}><option value="">All processed documents</option>{documents.map((document) => <option key={document.id} value={document.id}>{document.filename}</option>)}</select></div>
          <button className="new-chat" type="button" disabled={sending || messages.length === 0} onClick={() => resetConversation()}>+ New chat</button>
        </div>

        <div className="chat-messages" aria-live="polite" aria-relevant="additions" aria-busy={sending}>
          {loading ? <div className="chat-welcome" role="status"><span className="spinner" /><p>Loading your library…</p></div>
            : libraryError ? <div className="chat-welcome"><p className="error" role="alert">{libraryError}</p><button className="retry" onClick={() => window.location.reload()}>Try again</button></div>
              : documents.length === 0 ? <div className="chat-welcome"><span className="chat-symbol" aria-hidden="true">✦</span><h2>Give your questions a starting point.</h2><p>Upload a document first. For existing files,<br />choose Create chunks in your library.</p><a className="chat-link" href="/">Open document library ↗</a></div>
                : messages.length === 0 ? <div className="chat-welcome"><span className="chat-symbol" aria-hidden="true">✦</span><h2>Your documents have a lot to say.</h2><p>Ask a question, get a summary, or find a detail.<br />Answers come with source passages you can check.</p><div className="suggestions">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => { setInput(suggestion); inputRef.current?.focus(); }}>{suggestion}<span aria-hidden="true">↗</span></button>)}</div></div>
                  : messages.map((message) => <article key={message.id} className={`chat-message ${message.role}`} aria-label={message.role === 'user' ? 'Your message' : 'Answer'}>
                    <div className="message-avatar" aria-hidden="true">{message.role === 'user' ? 'You' : 'K'}</div>
                    <div className="message-body"><p className="message-label">{message.role === 'user' ? 'You' : 'Knowledge assistant'}</p><div className="message-text">{message.role === 'assistant' ? renderAnswer(message) : message.content}</div>
                      {!!message.sources?.length && <div className="sources"><p className="source-label">SOURCE PASSAGES</p>{message.sources.map((source) => <details className="source-card" key={source.chunk_id} id={`source-${message.id}-${source.citation}`}><summary><span className="source-number">{source.citation}</span><span>{source.filename}<small>{source.page_number ? `Page ${source.page_number}` : `Passage ${source.chunk_index + 1}`}</small></span><span className="source-expand" aria-hidden="true">+</span></summary><blockquote>{source.excerpt}</blockquote><a href={`/api/documents/${source.document_id}/download`}>Download original ↗</a></details>)}</div>}
                    </div>
                  </article>)}
          {sending && <div className="chat-message assistant" role="status"><div className="message-avatar" aria-hidden="true">K</div><div className="thinking"><span className="spinner" /> Searching your documents and writing an answer…</div></div>}
          <div ref={bottomRef} />
        </div>

        <div className="chat-composer">
          {error && <p className="error chat-error" role="alert">{error}</p>}
          <form onSubmit={send} aria-label="Ask a question"><label className="visually-hidden" htmlFor="chat-question">Your question</label><textarea id="chat-question" ref={inputRef} value={input} maxLength={2000} rows={2} placeholder="Ask something about your documents…" disabled={sending || loading || documents.length === 0} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><button type="submit" className="send-button" aria-label="Send question" disabled={!input.trim() || sending || loading || documents.length === 0}>{sending ? <span className="spinner" /> : '↑'}</button></form>
          <p className="chat-hint">Answers use your documents. Review the sources for important details.</p>
        </div>
      </section>
      <footer className="page-footer">A little less searching. A little more knowing.</footer>
    </main>
  );
}

export default Chat;
