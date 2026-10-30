import { useEffect, useRef, useState } from 'react';
import type { DragEvent, FormEvent } from 'react';
import './App.css';

interface DocumentRecord {
  id: string;
  filename: string;
  metadata: { size_bytes?: number; content_type?: string; status?: string; chunk_count?: number };
  needs_reprocessing?: boolean;
  chunk_count?: number;
  created_at: string;
  downloadable?: boolean;
}

const MAX_BYTES = 4 * 1024 * 1024;

function formatSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 16H6a4 4 0 0 1-.7-7.94A7 7 0 0 1 19 9a3.5 3.5 0 0 1-1 7h-2M12 20V10m-4 4 4-4 4 4" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selected, setSelected] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [libraryError, setLibraryError] = useState('');
  const [success, setSuccess] = useState('');
  const [database, setDatabase] = useState<'checking' | 'connected' | 'unavailable'>('checking');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/documents', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load your documents. Check that FastAPI and the database are running.');
        const body = await response.json();
        setDocuments(body.documents);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setLibraryError(err instanceof Error ? err.message : 'Could not load documents.');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    fetch('/api/health/db', { signal: controller.signal })
      .then((response) => { setDatabase(response.ok ? 'connected' : 'unavailable'); })
      .catch(() => { if (!controller.signal.aborted) setDatabase('unavailable'); });
    return () => controller.abort();
  }, []);

  function selectFile(file: File | undefined) {
    if (uploading) return;
    setError('');
    setSuccess('');
    if (!file) return;
    if (!/\.(pdf|txt)$/i.test(file.name)) {
      setSelected(null);
      setError('Please choose a PDF or TXT file.');
    } else if (file.size === 0 || file.size > MAX_BYTES) {
      setSelected(null);
      setError(file.size === 0 ? 'This file is empty. Please choose another.' : 'Please choose a file smaller than 4 MB.');
    } else {
      setSelected(file);
    }
    if (inputRef.current) inputRef.current.value = '';
  }

  function dropFile(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    if (uploading) return;
    if (event.dataTransfer.files.length !== 1) {
      setSelected(null);
      setError('Please upload one document at a time.');
      return;
    }
    selectFile(event.dataTransfer.files[0]);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || uploading) return;
    setUploading(true);
    setError('');
    setSuccess('');
    const form = new FormData();
    form.append('file', selected);
    try {
      const response = await fetch('/api/documents', { method: 'POST', body: form });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Upload failed. Please try again.');
      setDocuments((previous) => [{ ...body, downloadable: true }, ...previous].slice(0, 100));
      setLibraryError('');
      setDatabase('connected');
      setSuccess(`${body.filename} was saved with ${body.metadata.chunk_count} searchable chunks.`);
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  async function processDocument(document: DocumentRecord) {
    if (processingId || uploading) return;
    setProcessingId(document.id);
    setError('');
    setSuccess('');
    try {
      const response = await fetch(`/api/documents/${document.id}/process`, { method: 'POST' });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Could not process this document. Please try again.');
      setDocuments((previous) => previous.map((item) => item.id === document.id ? body : item));
      setSuccess(`${body.filename} is ready with ${body.metadata.chunk_count} chunks.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Document processing failed.');
    } finally {
      setProcessingId(null);
    }
  }

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Knowledge library home"><span className="brand-mark">K</span> Knowledge library</a>
        <div className="header-actions"><a className="chat-link" href="/chat">Chat with documents ↗</a><span className={`connection ${database}`}><span />{database === 'checking' ? 'Checking connection' : database === 'connected' ? 'Storage connected' : 'Storage unavailable'}</span></div>
      </header>

      <section className="intro">
        <p className="eyebrow">YOUR KNOWLEDGE, IN ONE PLACE</p>
        <h1>Start with a document.</h1>
        <p className="intro-copy">Bring your PDFs and notes together. Upload a document to start building your knowledge library.</p>
      </section>

      <div className="content-grid">
        <section className="upload-panel" aria-labelledby="upload-heading">
          <div className="section-heading"><span className="step">01</span><h2 id="upload-heading">Add a document</h2></div>
          <form onSubmit={upload} aria-busy={uploading}>
            <label className={`dropzone ${dragging ? 'dragging' : ''} ${uploading ? 'disabled' : ''}`}
              onDragOver={(event) => { event.preventDefault(); if (!uploading) setDragging(true); }}
              onDragLeave={() => setDragging(false)} onDrop={dropFile}>
              <input ref={inputRef} type="file" accept=".pdf,.txt" disabled={uploading}
                onChange={(event) => selectFile(event.target.files?.[0])} aria-label="Choose a PDF or TXT document" />
              <span className="upload-icon"><UploadIcon /></span>
              <strong>{selected ? 'Ready when you are.' : 'Drop your document here'}</strong>
              <span>or <span className="browse">browse files</span> on your device</span>
              <small>PDF or TXT · Up to 4 MB per file</small>
            </label>
            {selected && <div className="selected-file"><span className="file-type">{selected.name.split('.').pop()?.toUpperCase()}</span><div><strong>{selected.name}</strong><small>{formatSize(selected.size)}</small></div><button type="button" className="remove" onClick={() => setSelected(null)} disabled={uploading} aria-label="Remove selected file">×</button></div>}
            <button className="upload-button" type="submit" disabled={!selected || uploading || loading || !!processingId}>
              {uploading ? <><span className="spinner" /> Uploading &amp; processing…</> : <>Upload document <span aria-hidden="true">↗</span></>}
            </button>
            <div className="feedback" aria-live="polite">
              {error && <p className="error" role="alert">{error}</p>}
              {success && <p className="success">{success}</p>}
            </div>
          </form>
          <div className="note"><span aria-hidden="true">✦</span><p>Prepared for search, automatically.<br /><span>Text is split into chunks. Original files stay available.</span></p></div>
        </section>

        <section className="library-panel" aria-labelledby="library-heading">
          <div className="library-header"><div><p className="eyebrow">YOUR COLLECTION</p><h2 id="library-heading">Documents <span className="count">{documents.length}</span></h2></div><span className="library-label">LATEST UPLOADS</span></div>
          {loading ? <div className="empty-state" role="status"><span className="spinner" /> Loading your documents…</div>
            : libraryError ? <div className="empty-state"><p className="error" role="alert">{libraryError}</p><button className="retry" onClick={() => window.location.reload()}>Try again</button></div>
              : documents.length === 0 ? <div className="empty-state"><span className="empty-symbol" aria-hidden="true">▤</span><h3>Your library starts here</h3><p>Upload your first document.<br />It will appear here when it’s saved.</p></div>
                : <ul className="document-list">{documents.map((document) => <li className="document-row" key={document.id}>
                  <span className={`file-type ${document.filename.toLowerCase().endsWith('.pdf') ? 'pdf' : ''}`}>{document.filename.split('.').pop()?.toUpperCase()}</span>
                  <div className="document-info"><strong>{document.filename}</strong><p>{document.metadata.size_bytes != null ? formatSize(document.metadata.size_bytes) : 'Document'}<span>·</span>{new Date(document.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</p><p className="chunk-count">{document.chunk_count ?? document.metadata.chunk_count ?? 0} chunks</p></div>
                  {document.needs_reprocessing || document.metadata.status !== 'ready' || document.chunk_count === 0 ? <button className="process-button" disabled={!!processingId || uploading} onClick={() => processDocument(document)} aria-label={`Process ${document.filename}`}>{processingId === document.id ? 'Processing…' : 'Create chunks'}</button> : <span className="upload-status">Ready</span>}
                  {document.downloadable && <a className="download" href={`/api/documents/${document.id}/download`} aria-label={`Download ${document.filename}`} title="Download document">↓</a>}
                </li>)}</ul>}
          <p className="library-footer">Original documents · PDF &amp; plain text</p>
        </section>
      </div>
      <footer className="page-footer">A little less searching. A little more knowing.</footer>
    </main>
  );
}

export default App;
