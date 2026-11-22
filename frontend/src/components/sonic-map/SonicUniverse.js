import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Crosshair,
  Heart,
  Info,
  Layers,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Search,
  Share2,
  Sparkles,
  Volume2,
  VolumeX
} from 'lucide-react';
import { getSimilarTracks } from '../../services/pipeline';
import './SonicUniverse.css';

const FAVORITES_KEY = 'rebel-sonic-favorites';

const loadFavorites = () => {
  try {
    const stored = localStorage.getItem(FAVORITES_KEY);
    return stored ? new Set(JSON.parse(stored)) : new Set();
  } catch {
    return new Set();
  }
};

const saveFavorites = (favorites) => {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites]));
  } catch {
    // Ignore storage errors
  }
};

const getTrackId = (track) => String(track?.id || '');

const resolvePreviewUrl = (track) => {
  if (!track) return '';
  return (
    track.preview_url ||
    track.previewUrl ||
    track.bandcamp_url ||
    track.deezer_url ||
    track.youtube_url ||
    track.audio_url ||
    ''
  );
};

const vertexShaderSource = `
attribute vec3 aPosition;
attribute vec3 aColor;
attribute float aSize;
uniform mat4 uMatrix;
uniform float uPixelRatio;
varying vec3 vColor;

void main() {
  vec4 clip = uMatrix * vec4(aPosition, 1.0);
  gl_Position = clip;
  float perspectiveSize = aSize * (190.0 / max(35.0, clip.w));
  gl_PointSize = clamp(perspectiveSize * uPixelRatio, 3.0 * uPixelRatio, 30.0 * uPixelRatio);
  vColor = aColor;
}
`;

const fragmentShaderSource = `
precision mediump float;
varying vec3 vColor;

void main() {
  vec2 centered = gl_PointCoord * 2.0 - 1.0;
  float radius = dot(centered, centered);
  if (radius > 1.0) discard;
  float core = smoothstep(1.0, 0.08, radius);
  float halo = smoothstep(1.0, 0.35, radius);
  vec3 color = vColor * (0.8 + core * 1.5);
  gl_FragColor = vec4(color, max(core, halo * 0.55));
}
`;

const lineVertexShaderSource = `
attribute vec3 aPosition;
attribute vec3 aColor;
uniform mat4 uMatrix;
varying vec3 vColor;

void main() {
  gl_Position = uMatrix * vec4(aPosition, 1.0);
  vColor = aColor;
}
`;

const lineFragmentShaderSource = `
precision mediump float;
varying vec3 vColor;

void main() {
  gl_FragColor = vec4(vColor, 0.55);
}
`;

const FILTERS = [
  { id: 'all', label: 'All signals' },
  { id: 'full', label: 'CLAP full' },
  { id: 'approx', label: 'KNN approx' },
  { id: 'fallback', label: 'Fallback' }
];

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const normalize = (vector) => {
  const length = Math.hypot(vector[0], vector[1], vector[2]) || 1;
  return vector.map((value) => value / length);
};

const cross = (left, right) => [
  left[1] * right[2] - left[2] * right[1],
  left[2] * right[0] - left[0] * right[2],
  left[0] * right[1] - left[1] * right[0]
];

const dot = (left, right) => left[0] * right[0] + left[1] * right[1] + left[2] * right[2];

const perspective = (fieldOfView, aspect, near, far) => {
  const factor = 1 / Math.tan(fieldOfView / 2);
  const range = 1 / (near - far);
  return [
    factor / aspect, 0, 0, 0,
    0, factor, 0, 0,
    0, 0, (near + far) * range, -1,
    0, 0, near * far * range * 2, 0
  ];
};

const lookAt = (eye, target, up) => {
  const zAxis = normalize([eye[0] - target[0], eye[1] - target[1], eye[2] - target[2]]);
  const xAxis = normalize(cross(up, zAxis));
  const yAxis = cross(zAxis, xAxis);
  return [
    xAxis[0], yAxis[0], zAxis[0], 0,
    xAxis[1], yAxis[1], zAxis[1], 0,
    xAxis[2], yAxis[2], zAxis[2], 0,
    -dot(xAxis, eye), -dot(yAxis, eye), -dot(zAxis, eye), 1
  ];
};

const multiplyMatrices = (left, right) => {
  const result = new Array(16).fill(0);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      for (let index = 0; index < 4; index += 1) {
        result[column * 4 + row] += left[index * 4 + row] * right[column * 4 + index];
      }
    }
  }
  return result;
};

const transformPoint = (matrix, point) => [
  matrix[0] * point[0] + matrix[4] * point[1] + matrix[8] * point[2] + matrix[12],
  matrix[1] * point[0] + matrix[5] * point[1] + matrix[9] * point[2] + matrix[13],
  matrix[2] * point[0] + matrix[6] * point[1] + matrix[10] * point[2] + matrix[14],
  matrix[3] * point[0] + matrix[7] * point[1] + matrix[11] * point[2] + matrix[15]
];

const compileShader = (gl, type, source) => {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(message || 'Unable to compile WebGL shader');
  }
  return shader;
};

const createProgram = (gl, vertexSource, fragmentSource) => {
  const program = gl.createProgram();
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(message || 'Unable to link WebGL program');
  }
  return program;
};

export const trackPosition = (track) => {
  const position = track?.position;
  const rawValues = [position?.x, position?.y, position?.z];
  if (rawValues.some((value) => value === null || value === undefined || value === '')) return null;
  const values = rawValues.map(Number);
  return values.every(Number.isFinite) ? values : null;
};

const trackMethod = (track) => track?.positionMethod || track?.position_method || 'unpositioned';

export const methodGroup = (track) => {
  const method = trackMethod(track);
  if (method === 'clap_umap_full' || method === 'umap_full') return 'full';
  if (method === 'clap_knn_approx' || method === 'umap_approx') return 'approx';
  if (method === 'features_fallback' || method === 'pending') return 'fallback';
  return 'other';
};

const trackColor = (track, selected, relatedScore) => {
  if (selected) return [1, 0.96, 0.78];
  if (relatedScore !== undefined) {
    const strength = clamp(relatedScore, 0, 1);
    return [0.25 + strength * 0.2, 0.65 + strength * 0.3, 1];
  }
  if (methodGroup(track) === 'fallback') return [1, 0.45, 0.18];
  if (methodGroup(track) === 'approx') return [0.2, 0.88, 0.92];
  const color = track?.color || {};
  return [
    clamp(Number(color.r) || 0.62, 0.08, 1),
    clamp(Number(color.g) || 0.38, 0.08, 1),
    clamp(Number(color.b) || 0.92, 0.08, 1)
  ];
};

const methodLabel = (track) => {
  const group = methodGroup(track);
  if (group === 'full') return 'CLAP · UMAP full';
  if (group === 'approx') return 'CLAP · KNN approx';
  if (group === 'fallback') return 'Audio features fallback';
  return 'Position non versioned';
};

const formatMetric = (value) => (Number.isFinite(Number(value)) ? Number(value).toFixed(3) : '—');

const SonicUniverse = ({
  tracks = [],
  version = null,
  selectedTrackId = null,
  onSelectTrack,
  loading = false
}) => {
  const canvasRef = useRef(null);
  const audioRef = useRef(null);
  const selectTrackRef = useRef(onSelectTrack);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [genreFilter, setGenreFilter] = useState('all');
  const [energyFilter, setEnergyFilter] = useState('all');
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [favorites, setFavorites] = useState(() => loadFavorites());
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [similarTracks, setSimilarTracks] = useState([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const [similarError, setSimilarError] = useState('');
  const [webglError, setWebglError] = useState('');
  const [showGuide, setShowGuide] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [entryComplete, setEntryComplete] = useState(false);

  useEffect(() => {
    selectTrackRef.current = onSelectTrack;
  }, [onSelectTrack]);

  // Entry animation
  useEffect(() => {
    const timer = setTimeout(() => setEntryComplete(true), 100);
    return () => clearTimeout(timer);
  }, []);

  // Handle URL hash for share/deep-link
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash;
      if (hash.startsWith('#track=')) {
        const trackId = hash.slice(7);
        const track = tracks.find((t) => String(t.id) === trackId);
        if (track && selectTrackRef.current) {
          selectTrackRef.current(track);
        }
      }
    };
    handleHash();
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, [tracks]);

  const selectedId = selectedTrackId === null || selectedTrackId === undefined
    ? null
    : String(selectedTrackId);

  const positionedTracks = useMemo(
    () => tracks.filter((track) => trackPosition(track)),
    [tracks]
  );

  const selectedTrack = useMemo(
    () => positionedTracks.find((track) => String(track.id) === selectedId) || null,
    [positionedTracks, selectedId]
  );

  // Audio playback controls
  const currentPreviewUrl = useMemo(() => resolvePreviewUrl(selectedTrack), [selectedTrack]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (currentPreviewUrl) {
      audio.src = currentPreviewUrl;
      audio.load();
    } else {
      audio.pause();
      audio.src = '';
      setIsPlaying(false);
    }
  }, [currentPreviewUrl]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;
    const onTimeUpdate = () => setAudioProgress(audio.currentTime);
    const onDurationChange = () => setAudioDuration(audio.duration || 0);
    const onEnded = () => setIsPlaying(false);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
    };
  }, []);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !currentPreviewUrl) return;
    if (audio.paused) {
      audio.play().catch(() => setIsPlaying(false));
    } else {
      audio.pause();
    }
  }, [currentPreviewUrl]);

  const toggleMute = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !audio.muted;
    setIsMuted(audio.muted);
  }, []);

  const seekAudio = useCallback((event) => {
    const audio = audioRef.current;
    if (!audio || !audioDuration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    audio.currentTime = ratio * audioDuration;
  }, [audioDuration]);

  // Favorites management
  const toggleFavorite = useCallback((trackId) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(trackId)) {
        next.delete(trackId);
      } else {
        next.add(trackId);
      }
      saveFavorites(next);
      return next;
    });
  }, []);

  const isFavorite = useCallback((trackId) => favorites.has(trackId), [favorites]);

  // Share functionality
  const shareTrack = useCallback((track) => {
    const trackId = getTrackId(track);
    const url = `${window.location.origin}${window.location.pathname}#track=${trackId}`;
    window.history.replaceState(null, '', `#track=${trackId}`);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).catch(() => {});
    }
  }, []);

  // Extract unique genres for filter
  const availableGenres = useMemo(() => {
    const genres = new Set();
    positionedTracks.forEach((track) => {
      if (track.genre) genres.add(track.genre);
    });
    return ['all', ...Array.from(genres).sort()];
  }, [positionedTracks]);

  const visibleTracks = useMemo(() => {
    return positionedTracks.filter((track) => {
      // Method filter
      if (filter !== 'all' && methodGroup(track) !== filter) return false;
      // Genre filter
      if (genreFilter !== 'all' && track.genre !== genreFilter) return false;
      // Energy filter
      if (energyFilter !== 'all') {
        const energy = Number(track.energy || track.audio_features?.energy || 0);
        if (energyFilter === 'low' && energy > 0.33) return false;
        if (energyFilter === 'medium' && (energy <= 0.33 || energy > 0.66)) return false;
        if (energyFilter === 'high' && energy <= 0.66) return false;
      }
      // Favorites filter
      if (showFavoritesOnly && !favorites.has(getTrackId(track))) return false;
      return true;
    });
  }, [positionedTracks, filter, genreFilter, energyFilter, showFavoritesOnly, favorites]);

  const searchResults = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];
    return positionedTracks
      .filter((track) => `${track.title || ''} ${track.artist || ''}`.toLowerCase().includes(normalized))
      .slice(0, 6);
  }, [positionedTracks, query]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setSimilarTracks([]);
      setSimilarError('');
      return undefined;
    }
    setSimilarLoading(true);
    setSimilarError('');
    getSimilarTracks(selectedId, { limit: 8, minScore: 0 })
      .then((response) => {
        if (!cancelled) setSimilarTracks(response?.results || []);
      })
      .catch((error) => {
        if (!cancelled) {
          setSimilarTracks([]);
          setSimilarError(error.status === 409 ? 'Embedding not searchable yet' : error.message);
        }
      })
      .finally(() => {
        if (!cancelled) setSimilarLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const relatedScores = useMemo(
    () => new Map(similarTracks.map((track) => [String(track.track_id), Number(track.similarity_score)])),
    [similarTracks]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !visibleTracks.length) return undefined;
    const gl = canvas.getContext('webgl', {
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance'
    });
    if (!gl) {
      setWebglError('WebGL is unavailable. Use the accessible track list instead.');
      return undefined;
    }

    let pointProgram;
    let lineProgram;
    try {
      pointProgram = createProgram(gl, vertexShaderSource, fragmentShaderSource);
      lineProgram = createProgram(gl, lineVertexShaderSource, lineFragmentShaderSource);
    } catch (error) {
      setWebglError(error.message);
      return undefined;
    }
    setWebglError('');

    const renderTracks = visibleTracks.map((track) => ({ track, position: trackPosition(track) }));
    const positions = [];
    const colors = [];
    const sizes = [];
    renderTracks.forEach(({ track, position }) => {
      const relatedScore = relatedScores.get(String(track.id));
      positions.push(...position);
      colors.push(...trackColor(track, String(track.id) === selectedId, relatedScore));
      const baseSize = clamp(Number(track.size) || 2, 1, 5);
      sizes.push(String(track.id) === selectedId ? 18 : relatedScore !== undefined ? 11 + relatedScore * 5 : 6 + baseSize);
    });

    const selectedPosition = selectedTrack ? trackPosition(selectedTrack) : null;
    const linePositions = [];
    const lineColors = [];
    if (selectedPosition) {
      similarTracks.slice(0, 8).forEach((similar) => {
        const candidate = positionedTracks.find((track) => String(track.id) === String(similar.track_id));
        const candidatePosition = trackPosition(candidate);
        if (!candidatePosition || !visibleTracks.includes(candidate)) return;
        const score = clamp(Number(similar.similarity_score), 0, 1);
        linePositions.push(...selectedPosition, ...candidatePosition);
        lineColors.push(0.3, 0.7 + score * 0.3, 1, 0.3, 0.7 + score * 0.3, 1);
      });
    }

    const createBuffer = (data) => {
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
      return buffer;
    };

    const positionBuffer = createBuffer(positions);
    const colorBuffer = createBuffer(colors);
    const sizeBuffer = createBuffer(sizes);
    const linePositionBuffer = createBuffer(linePositions);
    const lineColorBuffer = createBuffer(lineColors);

    const pointLocations = {
      position: gl.getAttribLocation(pointProgram, 'aPosition'),
      color: gl.getAttribLocation(pointProgram, 'aColor'),
      size: gl.getAttribLocation(pointProgram, 'aSize'),
      matrix: gl.getUniformLocation(pointProgram, 'uMatrix'),
      pixelRatio: gl.getUniformLocation(pointProgram, 'uPixelRatio')
    };
    const lineLocations = {
      position: gl.getAttribLocation(lineProgram, 'aPosition'),
      color: gl.getAttribLocation(lineProgram, 'aColor'),
      matrix: gl.getUniformLocation(lineProgram, 'uMatrix')
    };

    const focus = selectedPosition || [0, 0, 0];
    const camera = {
      yaw: selectedPosition ? 0.65 : 0.8,
      pitch: selectedPosition ? 0.28 : 0.38,
      distance: selectedPosition ? 85 : 145,
      target: [...focus],
      dragging: false,
      moved: false,
      lastX: 0,
      lastY: 0
    };
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    let frameId;
    let lastMatrix = null;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.75);
      const width = Math.max(1, Math.round(rect.width * pixelRatio));
      const height = Math.max(1, Math.round(rect.height * pixelRatio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, width, height);
    };

    const bindAttribute = (buffer, location, size) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
    };

    const render = () => {
      resize();
      if (!camera.dragging && !reducedMotion && !selectedPosition) camera.yaw += 0.00045;
      const horizontal = Math.cos(camera.pitch) * camera.distance;
      const eye = [
        camera.target[0] + Math.sin(camera.yaw) * horizontal,
        camera.target[1] + Math.sin(camera.pitch) * camera.distance,
        camera.target[2] + Math.cos(camera.yaw) * horizontal
      ];
      const projection = perspective(Math.PI / 3.1, canvas.width / canvas.height, 0.1, 900);
      const view = lookAt(eye, camera.target, [0, 1, 0]);
      lastMatrix = multiplyMatrices(projection, view);

      gl.clearColor(0.012, 0.018, 0.035, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

      if (linePositions.length) {
        gl.useProgram(lineProgram);
        bindAttribute(linePositionBuffer, lineLocations.position, 3);
        bindAttribute(lineColorBuffer, lineLocations.color, 3);
        gl.uniformMatrix4fv(lineLocations.matrix, false, new Float32Array(lastMatrix));
        gl.drawArrays(gl.LINES, 0, linePositions.length / 3);
      }

      gl.useProgram(pointProgram);
      bindAttribute(positionBuffer, pointLocations.position, 3);
      bindAttribute(colorBuffer, pointLocations.color, 3);
      bindAttribute(sizeBuffer, pointLocations.size, 1);
      gl.uniformMatrix4fv(pointLocations.matrix, false, new Float32Array(lastMatrix));
      gl.uniform1f(pointLocations.pixelRatio, Math.min(window.devicePixelRatio || 1, 1.75));
      gl.drawArrays(gl.POINTS, 0, renderTracks.length);
      frameId = window.requestAnimationFrame(render);
    };

    const pickTrack = (clientX, clientY) => {
      if (!lastMatrix) return;
      const rect = canvas.getBoundingClientRect();
      let closest = null;
      let closestDistance = 22;
      renderTracks.forEach(({ track, position }) => {
        const clip = transformPoint(lastMatrix, position);
        if (clip[3] <= 0) return;
        const normalizedX = clip[0] / clip[3];
        const normalizedY = clip[1] / clip[3];
        const normalizedZ = clip[2] / clip[3];
        if (normalizedZ < -1 || normalizedZ > 1) return;
        const screenX = rect.left + ((normalizedX + 1) / 2) * rect.width;
        const screenY = rect.top + ((1 - normalizedY) / 2) * rect.height;
        const distance = Math.hypot(screenX - clientX, screenY - clientY);
        if (distance < closestDistance) {
          closest = track;
          closestDistance = distance;
        }
      });
      if (closest) selectTrackRef.current?.(closest);
    };

    const pointerDown = (event) => {
      camera.dragging = true;
      camera.moved = false;
      camera.lastX = event.clientX;
      camera.lastY = event.clientY;
      canvas.setPointerCapture?.(event.pointerId);
    };
    const pointerMove = (event) => {
      if (!camera.dragging) return;
      const deltaX = event.clientX - camera.lastX;
      const deltaY = event.clientY - camera.lastY;
      if (Math.abs(deltaX) + Math.abs(deltaY) > 2) camera.moved = true;
      camera.yaw -= deltaX * 0.006;
      camera.pitch = clamp(camera.pitch + deltaY * 0.0045, -1.25, 1.25);
      camera.lastX = event.clientX;
      camera.lastY = event.clientY;
    };
    const pointerUp = (event) => {
      if (!camera.moved) pickTrack(event.clientX, event.clientY);
      camera.dragging = false;
      canvas.releasePointerCapture?.(event.pointerId);
    };
    const wheel = (event) => {
      event.preventDefault();
      camera.distance = clamp(camera.distance * Math.exp(event.deltaY * 0.001), 24, 360);
    };
    const keyDown = (event) => {
      if (event.key === 'ArrowLeft') camera.yaw += 0.12;
      if (event.key === 'ArrowRight') camera.yaw -= 0.12;
      if (event.key === 'ArrowUp') camera.pitch = clamp(camera.pitch - 0.1, -1.25, 1.25);
      if (event.key === 'ArrowDown') camera.pitch = clamp(camera.pitch + 0.1, -1.25, 1.25);
      if (event.key === '+' || event.key === '=') camera.distance = clamp(camera.distance * 0.85, 24, 360);
      if (event.key === '-') camera.distance = clamp(camera.distance * 1.15, 24, 360);
      if (event.key.toLowerCase() === 'r') {
        camera.yaw = 0.8;
        camera.pitch = 0.38;
        camera.distance = 145;
        camera.target = [0, 0, 0];
      }
    };

    canvas.addEventListener('pointerdown', pointerDown);
    canvas.addEventListener('pointermove', pointerMove);
    canvas.addEventListener('pointerup', pointerUp);
    canvas.addEventListener('pointercancel', pointerUp);
    canvas.addEventListener('wheel', wheel, { passive: false });
    canvas.addEventListener('keydown', keyDown);
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    if (resizeObserver) {
      resizeObserver.observe(canvas);
    } else {
      window.addEventListener('resize', resize);
    }
    render();

    return () => {
      window.cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      if (!resizeObserver) window.removeEventListener('resize', resize);
      canvas.removeEventListener('pointerdown', pointerDown);
      canvas.removeEventListener('pointermove', pointerMove);
      canvas.removeEventListener('pointerup', pointerUp);
      canvas.removeEventListener('pointercancel', pointerUp);
      canvas.removeEventListener('wheel', wheel);
      canvas.removeEventListener('keydown', keyDown);
      [positionBuffer, colorBuffer, sizeBuffer, linePositionBuffer, lineColorBuffer].forEach((buffer) => gl.deleteBuffer(buffer));
      gl.deleteProgram(pointProgram);
      gl.deleteProgram(lineProgram);
    };
  }, [positionedTracks, relatedScores, selectedId, selectedTrack, similarTracks, visibleTracks]);

  const selectFromSearch = (track) => {
    setQuery('');
    selectTrackRef.current?.(track);
  };

  const selectSimilar = (similar) => {
    const track = positionedTracks.find((candidate) => String(candidate.id) === String(similar.track_id));
    if (track) selectTrackRef.current?.(track);
  };

  return (
    <section className="sonic-universe" aria-label="Interactive Sonic Map">
      <canvas
        ref={canvasRef}
        className="sonic-universe__canvas"
        tabIndex={0}
        aria-label="3D map of tracks. Drag to orbit, scroll to zoom, and select a luminous point."
      />

      <div className="sonic-universe__aurora" aria-hidden="true" />

      <header className="sonic-universe__topbar">
        <div className="sonic-universe__brand">
          <span className="sonic-universe__brand-icon"><Sparkles size={16} /></span>
          <div>
            <strong>REBEL Sonic Universe</strong>
            <span>{visibleTracks.length.toLocaleString()} positioned signals</span>
          </div>
        </div>

        <div className="sonic-universe__search">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Locate artist or track"
            aria-label="Search tracks in the Sonic Map"
          />
          {searchResults.length > 0 && (
            <div className="sonic-universe__search-results">
              {searchResults.map((track) => (
                <button key={track.id} type="button" onClick={() => selectFromSearch(track)}>
                  <strong>{track.title || 'Untitled'}</strong>
                  <span>{track.artist || 'Unknown artist'}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          className="sonic-universe__icon-button"
          onClick={() => setShowGuide((value) => !value)}
          aria-label="Show Sonic Map guide"
        >
          <Info size={17} />
        </button>
      </header>

      <div className="sonic-universe__filters" aria-label="Position method filters">
              <Layers size={15} />
        {FILTERS.map((item) => (
          <button
            type="button"
            key={item.id}
            className={filter === item.id ? 'active' : ''}
            onClick={() => setFilter(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {version && (
        <div className="sonic-universe__quality">
          <span>Map {String(version.id || '').slice(0, 8)}</span>
          <span>Trust {formatMetric(version.metrics?.trustworthiness)}</span>
          <span>Recall {formatMetric(version.metrics?.neighbor_recall)}</span>
        </div>
      )}

      {selectedTrack && (
        <aside className="sonic-universe__inspector">
          <div className="sonic-universe__inspector-kicker">
            <Crosshair size={14} /> Selected signal
          </div>
          <h3>{selectedTrack.title || 'Untitled'}</h3>
          <p className="sonic-universe__artist">{selectedTrack.artist || 'Unknown artist'}</p>
          <div className={`sonic-universe__method sonic-universe__method--${methodGroup(selectedTrack)}`}>
            {methodLabel(selectedTrack)}
          </div>

          {/* Audio Player */}
          <div className="sonic-universe__audio-player">
            <audio ref={audioRef} preload="metadata" />
            <div className="sonic-universe__audio-controls">
              <button
                type="button"
                className="sonic-universe__audio-btn"
                onClick={togglePlay}
                disabled={!currentPreviewUrl}
                aria-label={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <Pause size={16} /> : <Play size={16} />}
              </button>
              <button
                type="button"
                className="sonic-universe__audio-btn sonic-universe__audio-btn--small"
                onClick={toggleMute}
                aria-label={isMuted ? 'Unmute' : 'Mute'}
              >
                {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>
              <div
                className="sonic-universe__audio-progress"
                onClick={seekAudio}
                role="slider"
                aria-label="Audio progress"
                aria-valuemin={0}
                aria-valuemax={audioDuration}
                aria-valuenow={audioProgress}
              >
                <div
                  className="sonic-universe__audio-progress-bar"
                  style={{ width: audioDuration ? `${(audioProgress / audioDuration) * 100}%` : '0%' }}
                />
              </div>
              <span className="sonic-universe__audio-time">
                {audioDuration ? `${Math.floor(audioProgress / 60)}:${String(Math.floor(audioProgress % 60)).padStart(2, '0')}` : '--:--'}
              </span>
            </div>
            {!currentPreviewUrl && (
              <p className="sonic-universe__audio-unavailable">No preview available</p>
            )}
          </div>

          {/* Action buttons */}
          <div className="sonic-universe__actions">
            <button
              type="button"
              className={`sonic-universe__action-btn ${isFavorite(getTrackId(selectedTrack)) ? 'active' : ''}`}
              onClick={() => toggleFavorite(getTrackId(selectedTrack))}
              aria-label={isFavorite(getTrackId(selectedTrack)) ? 'Remove from favorites' : 'Add to favorites'}
            >
              <Heart size={15} fill={isFavorite(getTrackId(selectedTrack)) ? 'currentColor' : 'none'} />
            </button>
            <button
              type="button"
              className="sonic-universe__action-btn"
              onClick={() => shareTrack(selectedTrack)}
              aria-label="Share track"
            >
              <Share2 size={15} />
            </button>
          </div>

          <div className="sonic-universe__meta-grid">
            <span>Genre<strong>{selectedTrack.genre || 'Unmapped'}</strong></span>
            <span>Year<strong>{selectedTrack.year || '—'}</strong></span>
            <span>Version<strong>{String(selectedTrack.positionVersionId || 'legacy').slice(0, 8)}</strong></span>
            <span>Coordinates<strong>{trackPosition(selectedTrack)?.map((value) => value.toFixed(1)).join(' · ')}</strong></span>
          </div>

          <div className="sonic-universe__neighbors-title">
            <span>Closest ADN</span>
            {similarLoading && <Loader2 size={14} className="animate-spin" />}
          </div>
          {similarError && <p className="sonic-universe__muted">{similarError}</p>}
          <div className="sonic-universe__neighbors">
            {similarTracks.slice(0, 6).map((similar) => (
              <button key={similar.track_id} type="button" onClick={() => selectSimilar(similar)}>
                <span>
                  <strong>{similar.title || `Track ${similar.track_id}`}</strong>
                  <small>{similar.artist || 'Unknown artist'}</small>
                </span>
                <em>{(Number(similar.similarity_score) * 100).toFixed(1)}%</em>
              </button>
            ))}
          </div>
        </aside>
      )}

      {showGuide && (
        <div className="sonic-universe__guide">
          <button type="button" onClick={() => setShowGuide(false)} aria-label="Close guide">×</button>
          <h4>Read the universe</h4>
          <p>Drag or swipe to orbit. Scroll or pinch to zoom. Select a signal to retrieve its exact CLAP cosine neighbors.</p>
          <ul>
            <li><i className="legend-full" /> Full UMAP publication</li>
            <li><i className="legend-approx" /> KNN approximation</li>
            <li><i className="legend-fallback" /> Audio-feature fallback</li>
          </ul>
          <p>The 3D map is exploratory. Percentages in the inspector come from the original 512D CLAP space.</p>
        </div>
      )}

      <div className="sonic-universe__controls">
        <span><RotateCcw size={13} /> Drag orbit</span>
        <span>Scroll zoom</span>
        <span>Arrows / ± / R</span>
      </div>

      {(loading || webglError || (!loading && positionedTracks.length === 0)) && (
        <div className="sonic-universe__status">
          {loading ? <Loader2 size={22} className="animate-spin" /> : <AlertTriangle size={22} />}
          <strong>
            {loading
              ? 'Synchronizing Sonic Map…'
              : webglError
                ? '3D rendering unavailable'
                : 'No positioned tracks yet'}
          </strong>
          {webglError && <span>{webglError}</span>}
          {!webglError && !loading && positionedTracks.length === 0 && (
            <span>Run the positioning job to publish the first versioned map.</span>
          )}
        </div>
      )}

      {webglError && (
        <div className="sonic-universe__fallback-list">
          {visibleTracks.slice(0, 100).map((track) => (
            <button type="button" key={track.id} onClick={() => selectTrackRef.current?.(track)}>
              {track.title} — {track.artist}
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

export default SonicUniverse;
