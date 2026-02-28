// src/modules/tracks/trackController.js
const Track = require('../../models/Track');
const User = require('../user/userModel');
const path = require('path');
const fs = require('fs');
const { proofService } = require('../../../dist/account-abstraction');
const { parseFile } = require('music-metadata');
const pipelineService = require('./pipelineService');

// @desc    Upload a track
// @route   POST /api/tracks
// @access  Private (Artist only)
exports.uploadTrack = async (req, res) => {
  try {
    const { title, genre, description, tags } = req.body;
    
    // Vérifier si un fichier a été téléchargé
    if (!req.file) {
      return res.status(400).json({
        success: false,
        message: 'Please upload an audio file'
      });
    }
    const uploadsDir = path.join(__dirname, '../../../public/uploads/tracks');
    const audioFilePath = path.join(uploadsDir, req.file.filename);

    let duration = 0;
    try {
      const metadata = await parseFile(audioFilePath);
      duration = metadata.format.duration ? Math.round(metadata.format.duration) : 0;
    } catch (metadataError) {
      console.warn(`Unable to parse metadata for ${req.file.filename}:`, metadataError.message);
    }

    if (!duration) {
      try {
        const stats = fs.statSync(audioFilePath);
        duration = Math.round(stats.size / (192000 / 8)); // rudimentary fallback
      } catch (statError) {
        duration = 180;
      }
    }

    // Créer le track dans la base de données
    const track = await Track.create({
      title,
      genre,
      description,
      tags: tags ? tags.split(',').map(tag => tag.trim()) : [],
      artist: req.user.id,
      audioFile: req.file.filename,
      duration,
      isPublic: true
    });
    
    // Mettre à jour le compteur de tracks de l'utilisateur
    await User.findByIdAndUpdate(req.user.id, { $inc: { tracksCount: 1 } });

    // Synchroniser avec le pipeline audio (fire-and-forget)
    const publicBaseUrl = process.env.API_PUBLIC_URL || `http://localhost:${process.env.PORT || 5001}`;
    const audioUrl = `${publicBaseUrl.replace(/\/$/, '')}/uploads/tracks/${req.file.filename}`;
    pipelineService
      .ingestTrack({
        mongoTrackId: track._id.toString(),
        title,
        artist: req.user.username,
        genre,
        tags: tags ? tags.split(',').map(tag => tag.trim()) : [],
        description,
        durationSeconds: duration,
        audioUrl
      })
      .catch(err => {
        console.error('Pipeline ingestion failed:', err.message);
      });
    
    res.status(201).json({
      success: true,
      data: track
    });
  } catch (error) {
    console.error('Error uploading track:', error);
    res.status(500).json({
      success: false,
      message: 'Server error while uploading track'
    });
  }
};

// In trackController.js
exports.getTracks = async (req, res) => {
  try {
    const tracks = await Track.find({ isPublic: true }).populate('artist', 'username profilePicture');
    res.success({ tracks }, 'Tracks retrieved successfully');
  } catch (error) {
    console.error('Error retrieving tracks:', error);
    res.error('Server error while retrieving tracks', 500);
  }
};

exports.getUserTracks = async (req, res) => {
  try {
    const tracks = await Track.find({ artist: req.user.id }).sort('-createdAt');
    res.success(tracks, 'User tracks retrieved successfully');
  } catch (error) {
    console.error('Error retrieving user tracks:', error);
    res.error('Server error while retrieving user tracks', 500);
  }
};

// @desc    Generate blockchain proof for track
// @route   POST /api/tracks/:id/proof
// @access  Private
exports.createProof = async (req, res) => {
  try {
    const track = await Track.findById(req.params.id);
    
    if (!track) {
      return res.status(404).json({
        success: false,
        message: 'Track not found'
      });
    }
    
    // Vérifier la propriété
    if (track.artist.toString() !== req.user.id) {
      return res.status(403).json({
        success: false,
        message: 'You are not authorized to create a proof for this track'
      });
    }
    
    // Vérifier si l'utilisateur a une adresse Solana
    const user = await User.findById(req.user.id);
    if (!user.solanaAddress) {
      return res.status(400).json({
        success: false,
        message: 'You need a Solana wallet to create a proof'
      });
    }
    
    // Créer les métadonnées pour la preuve
    const metadata = {
      title: track.title,
      genre: track.genre,
      artist: user.username,
      createdAt: track.createdAt
    };
    
    // Créer la preuve sur la blockchain
    const proof = await proofService.createProofOfCreation(
      track._id.toString(),
      user._id.toString(),
      metadata
    );
    
    if (!proof.success) {
      return res.status(500).json({
        success: false,
        message: 'Failed to create blockchain proof',
        error: proof.error
      });
    }
    
    // Ajouter la preuve au tableau de preuves de l'utilisateur
    if (!user.proofs) {
      user.proofs = [];
    }
    
    user.proofs.push({
      trackId: track._id,
      timestamp: proof.timestamp,
      signature: proof.signature,
      transactionId: proof.transactionId
    });
    
    await user.save();
    
    res.status(200).json({
      success: true,
      data: {
        track: track._id,
        proofTimestamp: proof.timestamp,
        transactionId: proof.transactionId,
        signature: proof.signature
      }
    });
  } catch (error) {
    console.error('Error creating proof:', error);
    res.status(500).json({
      success: false,
      message: 'Server error while creating proof'
    });
  }
};

// @desc    Get proof for a track
// @route   GET /api/tracks/:id/proof
// @access  Private
exports.getProof = async (req, res) => {
  try {
    const track = await Track.findById(req.params.id);
    
    if (!track) {
      return res.status(404).json({
        success: false,
        message: 'Track not found'
      });
    }
    
    // Trouver l'utilisateur propriétaire du morceau
    const artist = await User.findById(track.artist);
    if (!artist) {
      return res.status(404).json({
        success: false,
        message: 'Track artist not found'
      });
    }
    
    // Trouver la preuve pour ce morceau
    const proof = artist.proofs && artist.proofs.find(p => 
      p.trackId.toString() === track._id.toString()
    );
    
    if (!proof) {
      return res.status(404).json({
        success: false,
        message: 'No proof found for this track'
      });
    }
    
    // Vérifier la preuve sur la blockchain
    let isVerified = false;
    try {
      if (proof.signature) {
        isVerified = await proofService.verifyProof(proof.signature);
      }
    } catch (err) {
      console.error('Error verifying proof:', err);
    }
    
    res.status(200).json({
      success: true,
      data: {
        track: {
          id: track._id,
          title: track.title,
          artist: artist.username
        },
        proof: {
          timestamp: proof.timestamp,
          signature: proof.signature,
          transactionId: proof.transactionId,
          verified: isVerified
        }
      }
    });
  } catch (error) {
    console.error('Error retrieving proof:', error);
    res.status(500).json({
      success: false,
      message: 'Server error while retrieving proof'
    });
  }
};
