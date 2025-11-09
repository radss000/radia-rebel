import React, { useCallback, useMemo, useState } from 'react';
import {
  Search,
  RefreshCcw,
  PlayCircle,
  AlertCircle,
  CheckCircle2,
  Loader2,
  XCircle,
  RotateCcw
} from 'lucide-react';
import {
  ANALYSIS_JOB_SEQUENCE,
  enqueueAnalysisJob,
  fetchPipelineSonicMap,
  getAnalysisJob,
  getPipelineTrackDetail,
  ingestPipelineTrack,
  searchAndIngestTrack,
  searchPipelineTracks
} from '../services/pipeline';

const MAP_URL = 'http://localhost:5001/sonic-map/index-new.html';

const statusColors = {
  idle: 'bg-costar-gray-dark text-costar-text-muted',
  queued: 'bg-blue-900/40 text-blue-300',
  running: 'bg-amber-900/40 text-amber-200',
  succeeded: 'bg-emerald-900/40 text-emerald-300',
  failed: 'bg-red-900/40 text-red-300'
};

const statusIcon = {
  idle: null,
  queued: <Loader2 size={14} className="animate-spin" />,
  running: <Loader2 size={14} className="animate-spin" />,
  succeeded: <CheckCircle2 size={14} />,
  failed: <AlertCircle size={14} />
};

const providerFromUrl = (url) => {
  if (!url) return undefined;
  const value = url.toLowerCase();
  if (value.includes('bandcamp')) return 'bandcamp';
  if (value.includes('spotify')) return 'spotify';
  if (value.includes('deezer')) return 'other'; // backend does not yet expose a dedicated Deezer provider
  if (value.includes('youtube') || value.includes('youtu.be')) return 'youtube_music';
  if (value.includes('discogs')) return 'discogs';
  return 'other';
};

const resolvePreviewUrl = (track) => {
  if (!track) return '';
  return (
    track.preview_url ||
    track.bandcamp_url ||
    track.deezer_url ||
    track.youtube_url ||
    track.audio_url ||
    ''
  );
};

const hasAnalysisData = (detail) => {
  if (!detail) return false;
  const hasPosition =
    detail.position_x !== null &&
    detail.position_y !== null &&
    detail.position_z !== null &&
    detail.position_x !== undefined &&
    detail.position_y !== undefined &&
    detail.position_z !== undefined;
  const hasEmbedding = Boolean(detail.embedding_id);
  return hasPosition && hasEmbedding;
};

const createInitialJobState = () =>
  ANALYSIS_JOB_SEQUENCE.reduce((acc, step) => {
    acc[step.type] = { status: 'idle', jobId: null, error: null };
    return acc;
  }, {});

const SonicMapPage = () => {
  const [iframeKey, setIframeKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [selectedTrackId, setSelectedTrackId] = useState(null);
  const [trackDetails, setTrackDetails] = useState({});
  const [previewUrl, setPreviewUrl] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [jobState, setJobState] = useState(() => createInitialJobState());
  const [isProcessing, setIsProcessing] = useState(false);
  const [mapRefreshing, setMapRefreshing] = useState(false);
  const [mapTrackCount, setMapTrackCount] = useState(null);
  const [lastMapRefresh, setLastMapRefresh] = useState(null);
  const [lastJobContext, setLastJobContext] = useState(null);
  const [autoArtist, setAutoArtist] = useState('');
  const [autoTitle, setAutoTitle] = useState('');
  const [autoPreviewOverride, setAutoPreviewOverride] = useState('');
  const [autoSelectedPreview, setAutoSelectedPreview] = useState(null);
  const [autoFormError, setAutoFormError] = useState('');
  const [autoSubmitting, setAutoSubmitting] = useState(false);

  const selectedDetail = selectedTrackId ? trackDetails[selectedTrackId] : null;

  const selectedAnalysisStatus = useMemo(() => {
    if (isProcessing) return 'processing';
    if (selectedDetail && hasAnalysisData(selectedDetail)) return 'complete';
    if (selectedDetail) return 'needs-analysis';
    return 'idle';
  }, [isProcessing, selectedDetail]);

  const handleAutoSearchSubmit = async (event) => {
    event.preventDefault();
    if (!autoArtist.trim() || !autoTitle.trim()) {
      setAutoFormError('Artist and title are required');
      return;
    }

    setAutoFormError('');
    setAutoSelectedPreview(null);
    setAnalysisError('');
    setJobState(createInitialJobState());
    setIsProcessing(true);
    setAutoSubmitting(true);

    try {
      const payload = {
        artist: autoArtist.trim(),
        title: autoTitle.trim(),
        requested_by: 'react-frontend'
      };

      if (autoPreviewOverride.trim()) {
        payload.fallback_url = autoPreviewOverride.trim();
      }

      const result = await searchAndIngestTrack(payload);
      setAutoSelectedPreview(result.selected_preview || null);
      const resolvedPreviewUrl = result.preview_source_url || result?.selected_preview?.webpage_url || autoPreviewOverride.trim();
      setPreviewUrl(resolvedPreviewUrl);
      setSelectedTrackId(result.track_id);
      await loadTrackDetail(result.track_id);

      const context = {
        trackId: result.track_id,
        audioAssetId: result.audio_asset_id,
        providerType: result.provider_type,
        providerTrackId: result.provider_track_id
      };
      setLastJobContext(context);

      await monitorExistingJobs(result.jobs || [], context);
      await refreshMapData();
    } catch (error) {
      const message = error.message || 'Failed to start analysis pipeline';
      setAutoFormError(message);
      setAnalysisError(message);
    } finally {
      setIsProcessing(false);
      setAutoSubmitting(false);
    }
  };

  const handleSearch = async (event) => {
    event.preventDefault();
    if (!searchTerm.trim()) {
      setSearchResults([]);
      setSelectedTrackId(null);
      setSearchError('');
      return;
    }

    setSearchLoading(true);
    setSearchError('');
    setAnalysisError('');

    try {
      const data = await searchPipelineTracks(searchTerm.trim(), 25);
      setSearchResults(Array.isArray(data.results) ? data.results : []);
      if (data.results?.length === 0) {
        setSelectedTrackId(null);
      }
    } catch (error) {
      setSearchError(error.message || 'Failed to search tracks');
    } finally {
      setSearchLoading(false);
    }
  };

  const loadTrackDetail = useCallback(
    async (trackId) => {
      try {
        const detail = await getPipelineTrackDetail(trackId);
        setTrackDetails((prev) => ({
          ...prev,
          [trackId]: detail
        }));
        const url = resolvePreviewUrl(detail);
        setPreviewUrl(url);
        return detail;
      } catch (error) {
        setAnalysisError(error.message || 'Failed to load track detail');
        throw error;
      }
    },
    []
  );

  const handleSelectTrack = async (track) => {
    if (!track?.id) return;
    setSelectedTrackId(track.id);
    setAnalysisError('');
    setJobState(createInitialJobState());
    setIsProcessing(false);

    if (!trackDetails[track.id]) {
      await loadTrackDetail(track.id);
    } else {
      setPreviewUrl(resolvePreviewUrl(trackDetails[track.id]));
    }
  };

  const updateJobStep = (type, updater) => {
    setJobState((prev) => {
      const current = prev[type] || { status: 'idle', jobId: null, error: null };
      const nextValue = typeof updater === 'function' ? updater(current) : updater;
      return {
        ...prev,
        [type]: nextValue
      };
    });
  };

  const pollJobUntilComplete = async (jobId, type) => {
    let attempts = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      if (attempts > 0) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      attempts += 1;

      const job = await getAnalysisJob(jobId);
      updateJobStep(type, (current) => ({
        ...current,
        status: job.status,
        jobId,
        error: job.error_message || null
      }));

      if (job.status === 'succeeded') {
        return job;
      }
      if (job.status === 'failed') {
        const message = job.error_message || `Job ${type} failed`;
        throw new Error(message);
      }
    }
  };

  const monitorExistingJobs = async (jobs = [], context = {}) => {
    if (!Array.isArray(jobs) || jobs.length === 0) {
      return;
    }

    const orderedJobs = ANALYSIS_JOB_SEQUENCE.map((step) =>
      jobs.find((job) => job?.type === step.type)
    ).filter(Boolean);

    for (const jobEntry of orderedJobs) {
      const jobId =
        jobEntry?.job?.id ||
        jobEntry?.job_id ||
        jobEntry?.jobId ||
        jobEntry?.id;

      if (!jobId) {
        // eslint-disable-next-line no-continue
        continue;
      }

      updateJobStep(jobEntry.type, {
        status: jobEntry?.job?.status || 'queued',
        jobId,
        error: null
      });

      await pollJobUntilComplete(jobId, jobEntry.type);

      if ((jobEntry.type === 'audio_features' || jobEntry.type === 'position') && context.trackId) {
        const refreshed = await getPipelineTrackDetail(context.trackId);
        setTrackDetails((prev) => ({
          ...prev,
          [context.trackId]: refreshed
        }));
      }
    }
  };

  const refreshMapData = useCallback(async () => {
    setMapRefreshing(true);
    try {
      const tracks = await fetchPipelineSonicMap(600);
      const count = Array.isArray(tracks) ? tracks.length : tracks?.length ?? null;
      setMapTrackCount(count);
      setLastMapRefresh(new Date());
      setIframeKey((prev) => prev + 1); // reload iframe to pull fresh data
    } catch (error) {
      setAnalysisError((prev) => prev || error.message || 'Failed to refresh sonic map');
    } finally {
      setMapRefreshing(false);
    }
  }, []);

  const buildIngestPayload = (detail) => {
    const url = previewUrl?.trim();

    if (!url) {
      throw new Error('Preview URL required to ingest track');
    }

    const fallbackTrackId = detail?.mongo_track_id || detail?.mongoTrackId || (detail?.id ? String(detail.id) : `pipeline-track-${Date.now()}`);

    const payload = {
      mongo_track_id: fallbackTrackId,
      title: detail?.title || 'Untitled track',
      artist: detail?.artist || detail?.artist_name || 'Unknown artist',
      audio_url: url,
      preview_source_url: url,
      preview_rights_scope: 'analysis_only'
    };
 
    const providerType = providerFromUrl(url);
    if (providerType) {
      payload.preview_provider_type = providerType;
    }

    if (detail?.mongo_track_id || detail?.mongoTrackId) {
      payload.mongo_track_id = detail.mongo_track_id || detail.mongoTrackId;
    }

    if (detail?.genre) {
      payload.genre = detail.genre;
    }

    const tags = detail?.tags || detail?.subgenres;
    if (Array.isArray(tags) && tags.length) {
      payload.tags = tags;
    } else if (typeof tags === 'string' && tags.trim()) {
      payload.tags = tags.split(',').map((tag) => tag.trim()).filter(Boolean);
    }

    const description = detail?.description_short || detail?.description;
    if (description) {
      payload.description = description;
    }

    const durationSeconds = detail?.duration_sec || detail?.duration_seconds;
    if (durationSeconds) {
      payload.duration_seconds = Number(durationSeconds);
    }

    const providerTrackId = detail?.provider_track_id || detail?.providerTrackId;
    if (providerTrackId) {
      payload.preview_provider_track_id = providerTrackId;
    }

    return payload;
  };

  const buildJobPayload = (type, context) => {
    const base = {
      job_type: type,
      requested_by: 'react-frontend'
    };

    if (type === 'preview_fetch' || type === 'audio_features') {
      base.audio_asset_id = context.audioAssetId;
    }

    if (type === 'audio_features' || type === 'embedding' || type === 'position') {
      base.track_id = context.trackId;
    }

    if (context.providerType && (type === 'preview_fetch' || type === 'audio_features')) {
      base.provider_type = context.providerType;
    }

    if (context.providerTrackId && (type === 'preview_fetch' || type === 'audio_features')) {
      base.provider_track_id = context.providerTrackId;
    }

    return base;
  };

  const runPipeline = useCallback(
    async (reuseContext = null) => {
      if (!selectedTrackId && !reuseContext?.trackId) {
        setAnalysisError('Select a track before running analysis');
        return;
      }

      const detail =
        (reuseContext && trackDetails[reuseContext.trackId]) ||
        selectedDetail ||
        (selectedTrackId ? await loadTrackDetail(selectedTrackId) : null);

      if (!detail) {
        setAnalysisError('No track details available for analysis');
        return;
      }

      const preview = previewUrl?.trim();
      if (!reuseContext && !preview) {
        setAnalysisError('Provide a preview URL to ingest the track');
        return;
      }

      setIsProcessing(true);
      setAnalysisError('');
      setJobState(createInitialJobState());
      setAutoSelectedPreview(null);

      try {
        let trackId = reuseContext?.trackId || detail.id;
        let audioAssetId = reuseContext?.audioAssetId || detail.audio_asset_id || detail.audioAssetId || null;

        if (!audioAssetId) {
          const ingestPayload = buildIngestPayload(detail);
          const ingestResult = await ingestPipelineTrack(ingestPayload);
          trackId = ingestResult.track_id || trackId;
          audioAssetId = ingestResult.audio_asset_id;

          const refreshedDetail = await getPipelineTrackDetail(trackId);
          setTrackDetails((prev) => ({
            ...prev,
            [trackId]: refreshedDetail
          }));
          setSelectedTrackId(trackId);
        }

        const providerType = providerFromUrl(preview || resolvePreviewUrl(detail));
        const context = {
          trackId,
          audioAssetId,
          providerType,
          providerTrackId: detail?.provider_track_id || detail?.providerTrackId || null
        };

        setLastJobContext(context);

        for (const step of ANALYSIS_JOB_SEQUENCE) {
          updateJobStep(step.type, {
            status: 'queued',
            jobId: null,
            error: null
          });

          const enqueueResult = await enqueueAnalysisJob(buildJobPayload(step.type, context));
          const jobId =
            enqueueResult?.job?.id ||
            enqueueResult?.job?.job_id ||
            enqueueResult?.queue_job_id ||
            enqueueResult?.id;

          if (!jobId) {
            throw new Error(`Unable to determine job id for ${step.label}`);
          }

          updateJobStep(step.type, {
            status: enqueueResult?.job?.status || 'queued',
            jobId,
            error: null
          });

          await pollJobUntilComplete(jobId, step.type);

          if (step.type === 'audio_features' || step.type === 'position') {
            const refreshed = await getPipelineTrackDetail(context.trackId);
            setTrackDetails((prev) => ({
              ...prev,
              [context.trackId]: refreshed
            }));
          }
        }

        await refreshMapData();
      } catch (error) {
        setAnalysisError(error.message || 'Analysis pipeline failed');
      } finally {
        setIsProcessing(false);
      }
    },
    [
      selectedTrackId,
      selectedDetail,
      previewUrl,
      trackDetails,
      loadTrackDetail,
      refreshMapData
    ]
  );

  const resultStatusLabel = (trackId) => {
    if (isProcessing && selectedTrackId === trackId) {
      return { label: 'Processing', tone: 'running' };
    }
    const detail = trackDetails[trackId];
    if (!detail) return { label: 'Unknown', tone: 'idle' };
    if (hasAnalysisData(detail)) return { label: 'Ready', tone: 'succeeded' };
    return { label: 'Needs analysis', tone: 'queued' };
  };

  const analysisStatusChip = () => {
    switch (selectedAnalysisStatus) {
      case 'processing':
        return <span className="px-2 py-1 rounded bg-amber-900/40 text-amber-200 text-xs">Processing...</span>;
      case 'complete':
        return <span className="px-2 py-1 rounded bg-emerald-900/40 text-emerald-300 text-xs">Analysis complete</span>;
      case 'needs-analysis':
        return <span className="px-2 py-1 rounded bg-blue-900/40 text-blue-200 text-xs">Needs analysis</span>;
      default:
        return <span className="px-2 py-1 rounded bg-costar-gray-dark text-costar-text-muted text-xs">Select a track</span>;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 pb-12 space-y-6">
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 space-y-6">
          <div className="costar-card space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Search & analyze a new track</h2>
            </div>

            <form onSubmit={handleAutoSearchSubmit} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs uppercase tracking-wide text-costar-text-muted mb-2">
                    Artist
                  </label>
                  <input
                    type="text"
                    value={autoArtist}
                    onChange={(event) => {
                      setAutoArtist(event.target.value);
                      setAutoFormError('');
                    }}
                    placeholder="Artist name"
                    className="input-costar"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs uppercase tracking-wide text-costar-text-muted mb-2">
                    Track title
                  </label>
                  <input
                    type="text"
                    value={autoTitle}
                    onChange={(event) => {
                      setAutoTitle(event.target.value);
                      setAutoFormError('');
                    }}
                    placeholder="Track title"
                    className="input-costar"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wide text-costar-text-muted mb-2">
                  Preview URL override (optional)
                </label>
                <input
                  type="url"
                  value={autoPreviewOverride}
                  onChange={(event) => {
                    setAutoPreviewOverride(event.target.value);
                    setAutoFormError('');
                  }}
                  placeholder="https://youtube.com/..."
                  className="input-costar"
                />
              </div>

              <button
                type="submit"
                disabled={autoSubmitting || isProcessing}
                className="btn-primary-costar w-full flex items-center justify-center gap-2"
              >
                {autoSubmitting ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Searching…
                  </>
                ) : (
                  <>
                    <Search size={16} />
                    Find & analyze
                  </>
                )}
              </button>
            </form>

            {autoFormError && (
              <div className="flex items-center gap-2 text-sm text-red-300 bg-red-900/20 border border-red-900/40 rounded p-2">
                <AlertCircle size={16} />
                <span>{autoFormError}</span>
              </div>
            )}

            {autoSelectedPreview && (
              <div className="bg-white/5 border border-white/10 rounded-lg p-3 text-xs text-costar-text-muted space-y-2">
                <div className="flex items-center justify-between text-white text-sm font-medium">
                  <span>{autoSelectedPreview.title || `${autoTitle} — ${autoArtist}`}</span>
                  <span className="uppercase tracking-wide text-[10px]">
                    {autoSelectedPreview.provider_type?.replace('_', ' ') || 'preview'}
                  </span>
                </div>
                {autoSelectedPreview.channel && (
                  <div>Source: {autoSelectedPreview.channel}</div>
                )}
                {typeof autoSelectedPreview.duration_seconds === 'number' && (
                  <div>Duration: {Math.round(autoSelectedPreview.duration_seconds)}s</div>
                )}
                {autoSelectedPreview.webpage_url && (
                  <a
                    href={autoSelectedPreview.webpage_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-emerald-300 hover:text-white transition-colors"
                  >
                    Open preview
                    <PlayCircle size={12} />
                  </a>
                )}
              </div>
            )}
          </div>

          <div className="costar-card">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-2xl font-semibold text-white">Sonic Map Pipeline</h1>
              {analysisStatusChip()}
            </div>

            <form onSubmit={handleSearch} className="relative">
              <Search size={18} className="absolute left-3 top-3 text-costar-text-muted" />
              <input
                type="text"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search tracks by title, artist, or album"
                className="input-costar pl-10 pr-32"
              />
              <button
                type="submit"
                disabled={searchLoading}
                className="absolute right-2 top-2 btn-secondary-costar px-4 py-2 text-sm"
              >
                {searchLoading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin" />
                    Searching...
                  </span>
                ) : (
                  'Search'
                )}
              </button>
            </form>

            {searchError && (
              <div className="mt-4 flex items-center text-red-300 text-sm">
                <AlertCircle size={16} className="mr-2" />
                {searchError}
              </div>
            )}
          </div>

          <div className="costar-card">
            <h2 className="text-lg font-semibold text-white mb-4">Results</h2>
            {searchResults.length === 0 ? (
              <p className="text-costar-text-muted text-sm">
                Search the catalog to find tracks that need processing.
              </p>
            ) : (
              <div className="space-y-3">
                {searchResults.map((track) => {
                  const { label, tone } = resultStatusLabel(track.id);
                  const isSelected = selectedTrackId === track.id;
                  return (
                    <button
                      key={track.id}
                      onClick={() => handleSelectTrack(track)}
                      className={`w-full text-left border rounded-lg p-4 transition-colors ${
                        isSelected
                          ? 'border-white bg-white/5'
                          : 'border-white/10 hover:border-white/20'
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="text-white font-medium">{track.title}</p>
                          <p className="text-sm text-costar-text-muted">{track.artist}</p>
                          {track.genre && (
                            <p className="text-xs text-costar-text-muted mt-1 uppercase tracking-wide">
                              {track.genre}
                            </p>
                          )}
                        </div>
                        <span className={`px-2 py-1 rounded text-xs ${statusColors[tone] || statusColors.idle}`}>
                          {label}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="w-full lg:w-[360px] space-y-6">
          <div className="costar-card space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Pipeline controls</h2>
              {selectedDetail && (
                <button
                  onClick={() => loadTrackDetail(selectedDetail.id)}
                  className="text-costar-text-muted hover:text-white transition-colors"
                  title="Reload track detail"
                >
                  <RefreshCcw size={16} />
                </button>
              )}
            </div>

            {selectedDetail ? (
              <div className="bg-white/5 rounded-lg p-3">
                <p className="text-white text-sm font-medium">{selectedDetail.title}</p>
                <p className="text-xs text-costar-text-muted">{selectedDetail.artist}</p>
                <div className="text-xs text-costar-text-muted mt-2 space-y-1">
                  <div>Track ID: {selectedDetail.id}</div>
                  <div>
                    Embedding:{' '}
                    {selectedDetail.embedding_id ? (
                      <span className="text-emerald-300">available</span>
                    ) : (
                      <span className="text-costar-text-muted">pending</span>
                    )}
                  </div>
                  <div>
                    Position:{' '}
                    {hasAnalysisData(selectedDetail) ? (
                      <span className="text-emerald-300">ready</span>
                    ) : (
                      <span className="text-costar-text-muted">pending</span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-costar-text-muted">
                Select a track to view details and orchestrate analysis jobs.
              </p>
            )}

            <div>
              <label className="block text-xs uppercase tracking-wide text-costar-text-muted mb-2">
                Preview URL (Bandcamp, Deezer, YouTube…)
              </label>
              <input
                type="url"
                value={previewUrl}
                onChange={(event) => setPreviewUrl(event.target.value)}
                placeholder="https://"
                className="input-costar"
              />
            </div>

            {analysisError && (
              <div className="flex items-center gap-2 text-sm text-red-300 bg-red-900/20 border border-red-900/40 rounded p-2">
                <AlertCircle size={16} />
                <span>{analysisError}</span>
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                onClick={() => runPipeline()}
                disabled={isProcessing || !selectedDetail}
                className="btn-primary-costar flex-1 flex items-center justify-center gap-2"
              >
                {isProcessing ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Processing…
                  </>
                ) : (
                  <>
                    <PlayCircle size={16} />
                    Run analysis
                  </>
                )}
              </button>
              <button
                onClick={() => refreshMapData()}
                disabled={mapRefreshing}
                className="btn-secondary-costar p-2"
                title="Refresh sonic map now"
              >
                {mapRefreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCcw size={16} />}
              </button>
            </div>

            {lastJobContext && !isProcessing && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => runPipeline(lastJobContext)}
                  className="btn-secondary-costar flex-1 flex items-center justify-center gap-2"
                >
                  <RotateCcw size={16} />
                  Retry last job
                </button>
                <button
                  onClick={() => {
                    setJobState(createInitialJobState());
                    setLastJobContext(null);
                    setIsProcessing(false);
                  }}
                  className="btn-ghost-costar p-2 text-red-300 hover:text-white"
                  title="Abort pipeline state"
                >
                  <XCircle size={16} />
                </button>
              </div>
            )}
          </div>

          <div className="costar-card">
            <h3 className="text-sm font-semibold text-white mb-3">Job progress</h3>
            <div className="space-y-2">
              {ANALYSIS_JOB_SEQUENCE.map((step) => {
                const state = jobState[step.type] || { status: 'idle', jobId: null, error: null };
                const chipStyle = statusColors[state.status] || statusColors.idle;
                return (
                  <div key={step.type} className="bg-white/5 rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-white">{step.label}</span>
                      <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${chipStyle}`}>
                        {statusIcon[state.status]}
                        {state.status}
                      </span>
                    </div>
                    {state.jobId && (
                      <div className="text-[11px] text-costar-text-muted mt-1">
                        Job ID: {state.jobId}
                      </div>
                    )}
                    {state.error && (
                      <div className="text-xs text-red-300 mt-1 flex items-center gap-1">
                        <AlertCircle size={12} />
                        {state.error}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="costar-card">
            <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
              <RefreshCcw size={16} />
              Sonic map refresh
            </h3>
            <p className="text-xs text-costar-text-muted leading-relaxed">
              The 3D map is reloaded automatically after the last job succeeds so new coordinates appear immediately.
              You can also force a refresh at any time.
            </p>
            <div className="mt-3 text-xs text-costar-text-muted space-y-1">
              <div>
                Last refresh:{' '}
                {lastMapRefresh ? lastMapRefresh.toLocaleTimeString() : 'not yet'}
              </div>
              <div>
                Track count:{' '}
                {mapTrackCount ?? '—'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="relative rounded-xl overflow-hidden shadow-lg border border-white/10">
        <iframe
          key={iframeKey}
          src={MAP_URL}
          title="Sonic Map"
          className="w-full h-[70vh]"
          allowFullScreen
        />
        {mapRefreshing && (
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center text-white text-sm gap-2">
            <Loader2 size={18} className="animate-spin" />
            Refreshing sonic map…
          </div>
        )}
      </div>
    </div>
  );
};

export default SonicMapPage;
