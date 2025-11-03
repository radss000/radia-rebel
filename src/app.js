// src/app.js
const express = require('express');
const dotenv = require('dotenv');
const path = require('path');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { URL } = require('url');
const proofRoutes = require('./modules/proof/proofRoutes');
const trackRoutes = require('./modules/tracks/trackRoutes');
const responseMiddleware = require('./middleware/responseMiddleware');

dotenv.config();

const userRoutes = require('./modules/user/userRoutes');
const magicRoutes = require('./modules/magic/magicRoutes');
const { errorResponse } = require('./utils/responseUtils');

const app = express();

const corsOrigins = (process.env.CORS_ORIGINS || 'http://localhost:3000')
  .split(',')
  .map(origin => origin.trim())
  .filter(Boolean);
const pipelineApiUrl = process.env.PIPELINE_API_URL || 'http://localhost:8000';
let pipelineOrigin = 'http://localhost:8000';
try {
  pipelineOrigin = new URL(pipelineApiUrl).origin;
} catch (err) {
  console.warn(`Invalid PIPELINE_API_URL provided (${pipelineApiUrl}), falling back to ${pipelineOrigin}`);
}

const fetchFn = globalThis.fetch
  ? globalThis.fetch.bind(globalThis)
  : ((...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args)));

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(cors({
  origin: corsOrigins.length ? corsOrigins : undefined,
  credentials: true
}));
app.use(helmet({
  crossOriginEmbedderPolicy: false,
  crossOriginResourcePolicy: false
}));
if (process.env.NODE_ENV !== 'test') {
  app.use(morgan('combined'));
}
app.use(responseMiddleware);

// ═══════════════════════════════════════════════════════════════
// PROXY SONIC MAP - DOIT ÊTRE ICI, AVANT LES ROUTES
// ═══════════════════════════════════════════════════════════════
app.get('/api/tracks/sonic-map', async (req, res) => {
  try {
    const response = await fetchFn(`${pipelineApiUrl.replace(/\/$/, '')}/api/tracks/sonic-map`);

    if (!response.ok) {
      throw new Error(`Python API returned ${response.status}`);
    }

    const data = await response.json();
    console.log(`✅ Proxied ${data.length} tracks from Python API`);
    res.json(data);
  } catch (error) {
    console.error('❌ Proxy error:', error.message);
    res.status(500).json({ 
      error: 'Failed to fetch tracks from Python API',
      message: error.message,
      hint: `Make sure Python API is running on ${pipelineApiUrl}`
    });
  }
});

// Serve static files
app.use('/uploads', express.static(path.join(__dirname, '../public/uploads')));
app.use('/sonicMapData.json', express.static(path.join(__dirname, '../public/sonicMapData.json')));
app.use('/play', express.static(path.join(__dirname, 'modules/play')));

// Sonic-map headers
app.use('/sonic-map', (req, res, next) => {
  if (corsOrigins.length) {
    res.setHeader('Access-Control-Allow-Origin', corsOrigins[0]);
    res.setHeader('X-Frame-Options', `ALLOW-FROM ${corsOrigins[0]}`);
  }
  next();
});

// Sonic-map CSP
app.use('/sonic-map', require('helmet')({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", 'https://cdn.babylonjs.com'],
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https://assets.babylonjs.com"],
      connectSrc: ["'self'", 'https://cdn.babylonjs.com', pipelineOrigin],
      fontSrc: ["'self'", "https://cdn.babylonjs.com"],
      objectSrc: ["'none'"],
      frameSrc: ["'self'", "https://www.youtube.com", "https://www.youtube-nocookie.com", "https://widget.deezer.com"],
      childSrc: ["'self'", "https://www.youtube.com", "https://www.youtube-nocookie.com", "https://widget.deezer.com"],
      frameAncestors: ["'self'"].concat(corsOrigins)
    }
  }
}));

app.use('/sonic-map', express.static(path.join(__dirname, '../public/sonic-map')));

// API Routes
app.use('/api/users', userRoutes);
app.use('/api/magic', magicRoutes);
app.use('/api/tracks', trackRoutes);
app.use('/api/proofs', proofRoutes);

// Root route
app.get('/', (req, res) => {
  res.success({ name: 'Rebellion Music API', version: '1.0.0' }, 'Welcome to the Rebellion music platform API');
});

app.get('/api/status', (req, res) => {
  res.success({
    status: 'ok',
    time: new Date().toISOString(),
    environment: process.env.NODE_ENV || 'development'
  });
});

app.get('/api/aa-status', (req, res) => {
  try {
    const { accountService } = require('../dist/account-abstraction');
    res.success({
      status: 'ok',
      solanaNetwork: process.env.SOLANA_NETWORK || 'devnet',
      adminPublicKey: accountService.solanaService.getAdminKeypair().publicKey.toString()
    });
  } catch (error) {
    console.error('Error in AA status check:', error);
    res.error('Account Abstraction service unavailable', 500);
  }
});

// Error handling
app.use((err, req, res, next) => {
  console.error(`[ERROR ${req.id}]:`, err);
  const statusCode = err.statusCode || 500;
  const message = err.message || 'Server error';
  const errors = err.errors || null;
  return errorResponse(res, statusCode, message, errors);
});

app.use((req, res) => {
  return errorResponse(res, 404, 'Route not found');
});

module.exports = app;
