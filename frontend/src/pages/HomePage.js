import React from 'react';
import { Music, Upload, Shield, LogIn, Award } from 'lucide-react';
import Logo from '../components/logo';

/**
 * HomePage Component - CoStar inspired design
 */
function HomePage({ user, navigateTo }) {
  return (
    <div className="max-w-4xl mx-auto animate-slide-up">
      {/* Hero Section */}
      <div className="text-center mb-16">
        <Logo size="xlarge" className="mb-6" />
        <p className="text-xl text-costar-text-muted max-w-2xl mx-auto">
          The definitive anti-algorithmic sanctuary for underground music
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
        <div className="costar-card group hover-lift">
          <div className="flex items-center mb-4">
            <div className="w-12 h-12 rounded-xl bg-costar-accent bg-opacity-20 flex items-center justify-center mr-4">
              <Music className="text-costar-accent" size={24} />
            </div>
            <h3 className="text-xl font-semibold">Explore the Feed</h3>
          </div>
          <p className="text-costar-text-muted mb-4">
            Discover new tracks, events, and challenges from the underground community.
          </p>
          <button 
            onClick={() => navigateTo('feed')}
            className="btn-primary-costar w-full"
          >
            Explore Feed
          </button>
        </div>

        <div className="costar-card group hover-lift">
          <div className="flex items-center mb-4">
            <div className="w-12 h-12 rounded-xl bg-costar-accent bg-opacity-20 flex items-center justify-center mr-4">
              <Award className="text-costar-accent" size={24} />
            </div>
            <h3 className="text-xl font-semibold">Sonic Map</h3>
          </div>
          <p className="text-costar-text-muted mb-4">
            Navigate music by sonic characteristics rather than algorithmic recommendations.
          </p>
          <button 
            onClick={() => navigateTo('sonic-map')}
            className="btn-secondary-costar w-full"
          >
            Open Sonic Map
          </button>
        </div>
      </div>

      {/* User-specific content */}
      {user ? (
        <div className="costar-card">
          <div className="flex items-center mb-6">
            <div className="w-16 h-16 rounded-full bg-costar-accent bg-opacity-20 flex items-center justify-center mr-4">
              {user.profilePicture ? (
                <img 
                  src={`http://localhost:5001/uploads/profiles/${user.profilePicture}`}
                  alt={user.username}
                  className="w-full h-full object-cover rounded-full"
                />
              ) : (
                <span className="text-2xl font-bold text-costar-accent">
                  {user.username?.charAt(0).toUpperCase() || user.email?.charAt(0).toUpperCase()}
                </span>
              )}
            </div>
            <div>
              <h2 className="text-2xl font-semibold">Welcome back, {user.username || user.email}</h2>
              <p className="text-costar-text-muted">Ready to create something amazing?</p>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <button 
              onClick={() => navigateTo('upload')}
              className="btn-primary-costar flex items-center justify-center space-x-2"
            >
              <Upload size={18} />
              <span>Upload Track</span>
            </button>
            <button 
              onClick={() => navigateTo('tracks')}
              className="btn-secondary-costar flex items-center justify-center space-x-2"
            >
              <Music size={18} />
              <span>My Tracks</span>
            </button>
            <button 
              onClick={() => navigateTo('proofs')}
              className="btn-ghost-costar flex items-center justify-center space-x-2"
            >
              <Shield size={18} />
              <span>My Proofs</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="costar-card text-center">
          <div className="mb-6">
            <div className="w-20 h-20 rounded-full bg-costar-accent bg-opacity-20 flex items-center justify-center mx-auto mb-4">
              <LogIn className="text-costar-accent" size={32} />
            </div>
            <h2 className="text-2xl font-semibold mb-2">Join the Revolution</h2>
            <p className="text-costar-text-muted max-w-md mx-auto">
              Sign up to upload tracks, create proofs of ownership, and connect with the underground music community.
            </p>
          </div>
          <button 
            onClick={() => navigateTo('login')}
            className="btn-primary-costar"
          >
            Get Started
          </button>
        </div>
      )}

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-12">
        <div className="text-center group">
          <div className="w-16 h-16 rounded-2xl bg-costar-accent bg-opacity-20 flex items-center justify-center mx-auto mb-4 group-hover:bg-opacity-30 transition-all">
            <Music className="text-costar-accent" size={24} />
          </div>
          <h3 className="font-semibold mb-2">Anti-Algorithm Discovery</h3>
          <p className="text-sm text-costar-text-muted">
            Human curation over AI recommendations
          </p>
        </div>
        <div className="text-center group">
          <div className="w-16 h-16 rounded-2xl bg-costar-accent bg-opacity-20 flex items-center justify-center mx-auto mb-4 group-hover:bg-opacity-30 transition-all">
            <Shield className="text-costar-accent" size={24} />
          </div>
          <h3 className="font-semibold mb-2">Proof of Creation</h3>
          <p className="text-sm text-costar-text-muted">
            Blockchain-verified ownership for your work
          </p>
        </div>
        <div className="text-center group">
          <div className="w-16 h-16 rounded-2xl bg-costar-accent bg-opacity-20 flex items-center justify-center mx-auto mb-4 group-hover:bg-opacity-30 transition-all">
            <Upload className="text-costar-accent" size={24} />
          </div>
          <h3 className="font-semibold mb-2">P2P Sharing</h3>
          <p className="text-sm text-costar-text-muted">
            Direct exchange with provenance verification
          </p>
        </div>
        <div className="text-center group">
          <div className="w-16 h-16 rounded-2xl bg-costar-accent bg-opacity-20 flex items-center justify-center mx-auto mb-4 group-hover:bg-opacity-30 transition-all">
            <Award className="text-costar-accent" size={24} />
          </div>
          <h3 className="font-semibold mb-2">Live Crates</h3>
          <p className="text-sm text-costar-text-muted">
            Gamified challenges and community voting
          </p>
        </div>
      </div>
    </div>
  );
}

export default HomePage;