import { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  Copy,
  FileAudio,
  Fingerprint,
  LoaderCircle,
  Radio,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  UploadCloud,
  X
} from 'lucide-react';
import { api } from './api.js';

function shorten(value, start = 7, end = 7) {
  if (!value) return '—';
  return `${value.slice(0, start)}…${value.slice(-end)}`;
}

function formatDate(value) {
  if (!value) return 'Pending';
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(value));
}

function CopyButton({ value }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <button className="icon-button" type="button" onClick={copy} aria-label="Copy value">
      {copied ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}

function Status({ health }) {
  const online = health?.status === 'ok';
  return (
    <div className={`network-status ${online ? 'online' : ''}`}>
      <span className="network-dot" />
      {online ? 'Devnet live' : 'Devnet unavailable'}
    </div>
  );
}

function UploadPanel({ configured, onCreated }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [artistName, setArtistName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);

  function selectFile(selectedFile) {
    if (!selectedFile) return;
    setFile(selectedFile);
    if (!title) setTitle(selectedFile.name.replace(/\.[^.]+$/, ''));
    setError('');
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) return setError('Choose an audio file first.');
    if (!configured) return setError('Configure and fund the devnet signer first.');

    setLoading(true);
    setError('');
    try {
      const proof = await api.createProof({ title, artistName, audioFile: file });
      onCreated(proof);
      setFile(null);
      setTitle('');
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel mint-panel">
      <div className="eyebrow"><Fingerprint size={15} /> New proof</div>
      <h2>Anchor your sound in time.</h2>
      <p className="panel-lead">
        The backend hashes the exact file bytes and records that fingerprint in a Solana PDA.
      </p>

      <form onSubmit={submit}>
        <label
          className={`dropzone ${dragging ? 'dragging' : ''} ${file ? 'selected' : ''}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            selectFile(event.dataTransfer.files[0]);
          }}
        >
          <input
            type="file"
            accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg"
            onChange={(event) => selectFile(event.target.files[0])}
          />
          {file ? <FileAudio size={34} /> : <UploadCloud size={34} />}
          <strong>{file ? file.name : 'Drop an audio file here'}</strong>
          <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : 'or click to browse · up to 50 MB'}</span>
        </label>

        <div className="form-grid">
          <label>
            <span>Work title</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Midnight Frequency" required />
          </label>
          <label>
            <span>Artist display name</span>
            <input value={artistName} onChange={(event) => setArtistName(event.target.value)} placeholder="Your artist name" required />
          </label>
        </div>

        {error && <div className="error-message"><X size={16} /> {error}</div>}

        <button className="primary-button" disabled={loading || !file || !configured}>
          {loading ? <LoaderCircle className="spin" size={19} /> : <ShieldCheck size={19} />}
          {loading ? 'Confirming on devnet…' : 'Create blockchain proof'}
        </button>
      </form>
    </section>
  );
}

function VerifyDialog({ proof, onClose }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function verify() {
    if (!file) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(await api.verifyProof(proof.id, file));
    } catch (verifyError) {
      setError(verifyError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <section className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" onClick={onClose}><X size={20} /></button>
        <div className="eyebrow"><SearchCheck size={15} /> Independent verification</div>
        <h2>Verify “{proof.title}”</h2>
        <p>Choose a file. Its SHA-256 fingerprint must match both the API record and the Solana account.</p>
        <label className="verify-file">
          <input type="file" accept="audio/*" onChange={(event) => setFile(event.target.files[0])} />
          <FileAudio size={22} />
          <span>{file?.name || 'Choose the audio file'}</span>
        </label>
        <button className="primary-button" disabled={!file || loading} onClick={verify}>
          {loading ? <LoaderCircle className="spin" size={19} /> : <SearchCheck size={19} />}
          Verify file and chain
        </button>
        {error && <div className="error-message"><X size={16} /> {error}</div>}
        {result && (
          <div className={`verify-result ${result.verified ? 'verified' : 'failed'}`}>
            {result.verified ? <ShieldCheck size={28} /> : <X size={28} />}
            <div>
              <strong>{result.verified ? 'Authenticity verified' : 'Verification failed'}</strong>
              <span>File hash: {result.hashMatches ? 'match' : 'different'} · On-chain account: {result.chainMatches ? 'match' : 'different'}</span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ProofCard({ proof, onVerify }) {
  return (
    <article className="proof-card">
      <div className="proof-card-top">
        <div className="proof-icon"><ShieldCheck size={22} /></div>
        <div>
          <h3>{proof.title}</h3>
          <p>{proof.artistName} · {formatDate(proof.onChainTimestampIso || proof.createdAt)}</p>
        </div>
        <span className="confirmed"><Check size={13} /> Confirmed</span>
      </div>
      <div className="proof-facts">
        <div>
          <span>Content fingerprint</span>
          <code>{shorten(proof.contentHash, 12, 12)}</code>
          <CopyButton value={proof.contentHash} />
        </div>
        <div>
          <span>Proof account</span>
          <code>{shorten(proof.pdaAddress)}</code>
          <CopyButton value={proof.pdaAddress} />
        </div>
        <div>
          <span>Signer</span>
          <code>{shorten(proof.artistPublicKey)}</code>
          <CopyButton value={proof.artistPublicKey} />
        </div>
      </div>
      <div className="proof-actions">
        <button className="secondary-button" onClick={() => onVerify(proof)}><SearchCheck size={17} /> Verify file</button>
        <a href={proof.explorerAccountUrl} target="_blank" rel="noreferrer">Open Solana account <ArrowUpRight size={16} /></a>
      </div>
    </article>
  );
}

export default function App() {
  const [proofs, setProofs] = useState([]);
  const [health, setHealth] = useState(null);
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [verifyProof, setVerifyProof] = useState(null);

  const configured = Boolean(runtimeConfig?.signerPublicKey);
  const totalBytes = useMemo(() => proofs.reduce((sum, proof) => sum + (proof.size || 0), 0), [proofs]);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [healthPayload, configPayload, proofPayload] = await Promise.all([
        api.getHealth(),
        api.getConfig(),
        api.listProofs()
      ]);
      setHealth(healthPayload);
      setRuntimeConfig(configPayload);
      setProofs(proofPayload);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="app-shell">
      <header>
        <div className="brand-mark"><Radio size={21} /></div>
        <div className="brand"><strong>RADIA</strong><span>PROOF</span></div>
        <nav><a href="#create">Create</a><a href="#proofs">Registry</a></nav>
        <Status health={health} />
      </header>

      <main>
        <section className="hero">
          <div>
            <div className="eyebrow"><span className="pulse" /> Solana timestamp protocol</div>
            <h1>Your sound.<br /><em>Provably yours.</em></h1>
            <p>Create a tamper-evident timestamp for any audio master. The file stays local to the request; only its SHA-256 fingerprint is written on-chain.</p>
          </div>
          <div className="hero-stats">
            <div><strong>{proofs.length}</strong><span>proofs indexed</span></div>
            <div><strong>{(totalBytes / 1024 / 1024).toFixed(1)} MB</strong><span>audio fingerprinted</span></div>
            <div><strong>32 bytes</strong><span>stored per hash</span></div>
          </div>
        </section>

        {error && <div className="global-error">API unavailable: {error} <button onClick={load}>Retry</button></div>}
        {!configured && !loading && (
          <div className="setup-banner">
            <Fingerprint size={22} />
            <div><strong>Devnet signer required</strong><span>Run <code>npm run keypair:generate</code>, fund the displayed address, then restart the API.</span></div>
          </div>
        )}

        <div id="create" className="content-grid">
          <UploadPanel configured={configured} onCreated={(proof) => setProofs((current) => [proof, ...current])} />
          <aside className="panel protocol-panel">
            <div className="eyebrow">Protocol details</div>
            <h2>What gets recorded?</h2>
            <div className="protocol-step"><span>01</span><div><strong>SHA-256 fingerprint</strong><p>A deterministic 32-byte digest of the uploaded file.</p></div></div>
            <div className="protocol-step"><span>02</span><div><strong>Creator signer</strong><p>The public key that funds and signs the proof transaction.</p></div></div>
            <div className="protocol-step"><span>03</span><div><strong>Network time</strong><p>The trusted Solana clock captured by the program.</p></div></div>
            <div className="program-box">
              <span>Program ID</span>
              <code>{shorten(runtimeConfig?.programId || '', 8, 8)}</code>
              {runtimeConfig?.programId && <CopyButton value={runtimeConfig.programId} />}
            </div>
          </aside>
        </div>

        <section id="proofs" className="registry">
          <div className="section-heading">
            <div><div className="eyebrow">Local registry</div><h2>Confirmed proofs</h2></div>
            <button className="refresh-button" onClick={load} disabled={loading}><RefreshCw className={loading ? 'spin' : ''} size={17} /> Refresh</button>
          </div>
          {proofs.length ? (
            <div className="proof-list">{proofs.map((proof) => <ProofCard key={proof.id} proof={proof} onVerify={setVerifyProof} />)}</div>
          ) : (
            <div className="empty-state"><ShieldCheck size={38} /><strong>No proofs yet</strong><span>Your first confirmed devnet proof will appear here.</span></div>
          )}
        </section>
      </main>

      <footer><span>Radia Proof · Solana devnet</span><span>Audio never persists on the server</span></footer>
      {verifyProof && <VerifyDialog proof={verifyProof} onClose={() => setVerifyProof(null)} />}
    </div>
  );
}
