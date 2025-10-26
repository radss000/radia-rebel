import React, { useState, useEffect } from 'react';
import { Magic } from 'magic-sdk';
import { OAuthExtension } from '@magic-ext/oauth';
import FeedPage from './pages/FeedPage';
import TrackProofButton from './components/TrackProofButton';
import SonicMapPage from './pages/SonicMapPage';

// Icons
import { Music, Upload, Shield, User, LogOut, LogIn, Award, HelpCircle, Home, Menu, X, ArrowLeft, Download, ExternalLink, AlertTriangle, CheckCircle, Clock, Calendar, MapPin, Heart, MessageCircle, Share, Play, Edit, Delete } from 'lucide-react';

/**
 * Main App Component - CoStar-inspired Black & White Design
 */
function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [magicSDK, setMagicSDK] = useState(null);
  const [currentPage, setCurrentPage] = useState('home');
  const [error, setError] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);

  // Initialize Magic SDK and check user state
  useEffect(() => {
    const initMagic = async () => {
      try {
        const magic = new Magic('pk_live_DAE97419AE6EBC48', {
          extensions: []
        });
        setMagicSDK(magic);
        
        const isLoggedIn = await magic.user.isLoggedIn();
        
        if (isLoggedIn) {
          try {
            const metadata = await magic.user.getInfo();
            const token = localStorage.getItem('token');
            
            if (token) {
              try {
                const response = await fetch('http://localhost:5001/api/users/profile', {
                  headers: {
                    'Authorization': `Bearer ${token}`
                  }
                });
                
                if (response.ok) {
                  const userData = await response.json();
                  if (userData.success) {
                    setUser({
                      ...userData.data,
                      token
                    });
                  }
                } else {
                  localStorage.removeItem('token');
                }
              } catch (error) {
                localStorage.removeItem('token');
              }
            }
          } catch (metadataError) {
            console.error('Error getting user metadata:', metadataError);
          }
        }
      } catch (error) {
        console.error('Error initializing Magic:', error);
        setError('Failed to initialize authentication system');
      } finally {
        setLoading(false);
      }
    };
    
    initMagic();
  }, []);

  const handleLogout = async () => {
    if (magicSDK) {
      try {
        await magicSDK.user.logout();
        localStorage.removeItem('token');
        setUser(null);
        setCurrentPage('home');
        setMenuOpen(false);
      } catch (error) {
        console.error('Error logging out:', error);
        setError('Failed to log out');
      }
    }
  };

  const navigate = (page) => {
    setCurrentPage(page);
    setMenuOpen(false);
  };

  // Render current page
  const renderPage = () => {
    switch(currentPage) {
      case 'login':
        return <LoginPage 
                 onBack={() => navigate('home')} 
                 magicSDK={magicSDK} 
                 setUser={setUser} 
                 navigateTo={navigate}
               />;
      case 'profile':
        return user ? (
          <ProfilePage user={user} setUser={setUser} onBack={() => navigate('home')} />
        ) : (
          <LoginPage 
            onBack={() => navigate('home')} 
            magicSDK={magicSDK} 
            setUser={setUser} 
            navigateTo={navigate}
          />
        );
      case 'tracks':
        return user ? (
          <TracksPage user={user} onBack={() => navigate('home')} navigateTo={navigate} />
        ) : (
          <LoginPage 
            onBack={() => navigate('home')} 
            magicSDK={magicSDK} 
            setUser={setUser} 
            navigateTo={navigate}
          />
        );
      case 'upload':
        return user ? (
          <UploadPage user={user} onBack={() => navigate('home')} />
        ) : (
          <LoginPage 
            onBack={() => navigate('home')} 
            magicSDK={magicSDK} 
            setUser={setUser} 
            navigateTo={navigate}
          />
        );
      case 'proofs':
        return user ? (
          <ProofsPage 
            user={user} 
            onBack={() => navigate('home')} 
            navigateTo={navigate}
          />
        ) : (
          <LoginPage 
            onBack={() => navigate('home')} 
            magicSDK={magicSDK} 
            setUser={setUser} 
            navigateTo={navigate}
          />
        );
      case 'feed':
        return user ? (
          <FeedPage user={user} navigateTo={navigate} />
        ) : (
          <LoginPage 
            onBack={() => navigate('home')} 
            magicSDK={magicSDK} 
            setUser={setUser} 
            navigateTo={navigate}
          />
        );
      case 'help':
        return <HelpPage onBack={() => navigate('home')} />;
      case 'sonic-map':
        return <SonicMapPage />;
      default:
        return <HomePage user={user} navigateTo={navigate} />;
    }
  };

  return (
    <div className="main-container">
      {/* Header with navigation */}
      <header className="header-costar">
        <div className="max-w-7xl mx-auto">
          <div className="flex justify-between items-center">
            {/* Logo */}
            <div className="flex items-center">
              <img 
                src="https://s17.aconvert.com/convert/p3r68-cdx67/txwln-08ufs.svg" 
                alt="REBEL" 
                className="h-8 w-auto"
              />
            </div>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center space-x-8">
              <NavButton onClick={() => navigate('home')} active={currentPage === 'home'}>
                Home
              </NavButton>
              <NavButton onClick={() => navigate('feed')} active={currentPage === 'feed'}>
                Feed
              </NavButton>
              <NavButton onClick={() => navigate('sonic-map')} active={currentPage === 'sonic-map'}>
                Sonic Map
              </NavButton>
              {user && (
                <>
                  <NavButton onClick={() => navigate('tracks')} active={currentPage === 'tracks'}>
                    My Tracks
                  </NavButton>
                  <NavButton onClick={() => navigate('upload')} active={currentPage === 'upload'}>
                    Upload
                  </NavButton>
                  <NavButton onClick={() => navigate('proofs')} active={currentPage === 'proofs'}>
                    Proofs
                  </NavButton>
                </>
              )}
            </nav>

            {/* User actions */}
            <div className="hidden lg:flex items-center space-x-4">
              {user ? (
                <div className="flex items-center space-x-4">
                  <button
                    onClick={() => navigate('profile')}
                    className="flex items-center space-x-2 text-costar-text-light hover:text-white transition-colors"
                  >
                    <div className="w-8 h-8 rounded-full bg-costar-gray-dark flex items-center justify-center">
                      {user.profilePicture ? (
                        <img 
                          src={`http://localhost:5001/uploads/profiles/${user.profilePicture}`}
                          alt={user.username}
                          className="w-full h-full object-cover rounded-full"
                        />
                      ) : (
                        <span className="text-sm font-medium">
                          {user.username?.charAt(0).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span className="text-sm">{user.username}</span>
                  </button>
                  <button
                    onClick={handleLogout}
                    className="text-costar-text-light hover:text-white transition-colors"
                  >
                    <LogOut size={20} />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => navigate('login')}
                  className="btn-primary-costar"
                >
                  Sign In
                </button>
              )}
            </div>

            {/* Mobile menu button */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="lg:hidden text-costar-text-light hover:text-white transition-colors"
            >
              {menuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {menuOpen && (
          <div className="lg:hidden bg-costar-dark border-t border-costar-border">
            <div className="px-4 py-4 space-y-3">
              <MobileNavButton onClick={() => navigate('home')} active={currentPage === 'home'}>
                <Home size={20} />
                <span>Home</span>
              </MobileNavButton>
              <MobileNavButton onClick={() => navigate('feed')} active={currentPage === 'feed'}>
                <Music size={20} />
                <span>Feed</span>
              </MobileNavButton>
              <MobileNavButton onClick={() => navigate('sonic-map')} active={currentPage === 'sonic-map'}>
                <Award size={20} />
                <span>Sonic Map</span>
              </MobileNavButton>
              {user ? (
                <>
                  <MobileNavButton onClick={() => navigate('tracks')} active={currentPage === 'tracks'}>
                    <Music size={20} />
                    <span>My Tracks</span>
                  </MobileNavButton>
                  <MobileNavButton onClick={() => navigate('upload')} active={currentPage === 'upload'}>
                    <Upload size={20} />
                    <span>Upload</span>
                  </MobileNavButton>
                  <MobileNavButton onClick={() => navigate('proofs')} active={currentPage === 'proofs'}>
                    <Shield size={20} />
                    <span>Proofs</span>
                  </MobileNavButton>
                  <MobileNavButton onClick={() => navigate('profile')} active={currentPage === 'profile'}>
                    <User size={20} />
                    <span>Profile</span>
                  </MobileNavButton>
                  <MobileNavButton onClick={handleLogout}>
                    <LogOut size={20} />
                    <span>Sign Out</span>
                  </MobileNavButton>
                </>
              ) : (
                <MobileNavButton onClick={() => navigate('login')} active={currentPage === 'login'}>
                  <LogIn size={20} />
                  <span>Sign In</span>
                </MobileNavButton>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Main Content */}
      <main className="min-h-[calc(100vh-80px)]">
        {loading ? (
          <div className="flex items-center justify-center min-h-[50vh]">
            <div className="loading-costar"></div>
          </div>
        ) : (
          renderPage()
        )}
      </main>

      {/* Error Toast */}
      {error && (
        <div className="notification-costar error-costar">
          <div className="flex items-center space-x-2">
            <span>{error}</span>
            <button 
              onClick={() => setError('')}
              className="text-red-300 hover:text-white"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Navigation Components
function NavButton({ children, onClick, active = false }) {
  return (
    <button
      onClick={onClick}
      className={`nav-link-costar ${active ? 'nav-link-active' : ''}`}
    >
      {children}
    </button>
  );
}

function MobileNavButton({ children, onClick, active = false }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center space-x-3 w-full p-3 rounded-lg transition-colors ${
        active 
          ? 'bg-white bg-opacity-10 text-white' 
          : 'text-costar-text-light hover:text-white hover:bg-white hover:bg-opacity-10'
      }`}
    >
      {children}
    </button>
  );
}

// HomePage component with CoStar-inspired design
function HomePage({ user, navigateTo }) {
  return (
    <div className="max-w-5xl mx-auto px-4 py-12">
      {/* Hero Section with Logo */}
      <div className="text-center mb-16">
        <div className="flex justify-center mb-8">
          <img 
            src="https://s17.aconvert.com/convert/p3r68-cdx67/txwln-08ufs.svg" 
            alt="REBEL" 
            className="h-20 w-auto"
          />
        </div>
        <p className="text-lg text-costar-text-light max-w-2xl mx-auto">
          The anti-algorithmic sanctuary for underground music, where human curation 
          trumps AI recommendations.
        </p>
      </div>

      {/* About Section */}
      <div className="about-section">
        <div className="about-card">
          <h2 className="text-section-title mb-4">Our Vision</h2>
          <p className="text-costar-text-muted mb-4">
            REBEL is the definitive anti-algorithmic sanctuary for underground music, 
            where human curation trumps AI recommendations, restoring cultural value and 
            financial sustainability to authentic electronic and experimental music scenes.
          </p>
          <p className="text-costar-text-muted">
            We rebuild the discovery-to-monetization pipeline through a decentralized ecosystem 
            where fans, DJs, and micro-labels connect directly, underpinned by transparent Web3 
            infrastructure.
          </p>
        </div>

        <div className="about-card">
          <h2 className="text-section-title mb-4">Get Started</h2>
          {user ? (
            <div>
              <p className="text-costar-text-muted mb-4">
                Welcome, <span className="text-white font-medium">{user.username || user.email}</span>!
              </p>
              <div className="feature-grid">
                <div className="feature-item hover-lift cursor-pointer" onClick={() => navigateTo('upload')}>
                  <div className="flex items-center space-x-2 mb-2">
                    <Upload size={16} />
                    <span className="feature-title">Upload a new track</span>
                  </div>
                  <p className="feature-description">Share your music with the community</p>
                </div>
                <div className="feature-item hover-lift cursor-pointer" onClick={() => navigateTo('tracks')}>
                  <div className="flex items-center space-x-2 mb-2">
                    <Music size={16} />
                    <span className="feature-title">Manage your tracks</span>
                  </div>
                  <p className="feature-description">View and edit your uploaded music</p>
                </div>
                <div className="feature-item hover-lift cursor-pointer" onClick={() => navigateTo('proofs')}>
                  <div className="flex items-center space-x-2 mb-2">
                    <Shield size={16} />
                    <span className="feature-title">View your ownership proofs</span>
                  </div>
                  <p className="feature-description">Manage blockchain timestamp proofs</p>
                </div>
                <div className="feature-item hover-lift cursor-pointer" onClick={() => navigateTo('feed')}>
                  <div className="flex items-center space-x-2 mb-2">
                    <Home size={16} />
                    <span className="feature-title">Explore the Feed</span>
                  </div>
                  <p className="feature-description">Discover new underground music</p>
                </div>
              </div>
            </div>
          ) : (
            <div>
              <p className="text-costar-text-muted mb-4">
                Join the community and start sharing your music with true ownership.
              </p>
              <button 
                onClick={() => navigateTo('login')}
                className="btn-primary-costar flex items-center space-x-2"
              >
                <LogIn size={16} />
                <span>Login with Magic Link</span>
              </button>
            </div>
          )}
        </div>
        
        <div className="about-card">
          <h2 className="text-section-title mb-4">Core Features</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="feature-item text-center hover-lift cursor-pointer" onClick={() => navigateTo('sonic-map')}>
              <div className="w-10 h-10 rounded-lg bg-costar-gray-dark flex items-center justify-center mb-3 mx-auto">
                <Music size={20} />
              </div>
              <h3 className="feature-title">Sonic Map</h3>
              <p className="feature-description mt-1">Visual interface representing music by sonic characteristics</p>
            </div>
            <div className="feature-item text-center hover-lift">
              <div className="w-10 h-10 rounded-lg bg-costar-gray-dark flex items-center justify-center mb-3 mx-auto">
                <Upload size={20} />
              </div>
              <h3 className="feature-title">P2P Sharing</h3>
              <p className="feature-description mt-1">Decentralized exchange for rare tracks with provenance verification</p>
            </div>
            <div className="feature-item text-center hover-lift">
              <div className="w-10 h-10 rounded-lg bg-costar-gray-dark flex items-center justify-center mb-3 mx-auto">
                <Award size={20} />
              </div>
              <h3 className="feature-title">Live Crates</h3>
              <p className="feature-description mt-1">Time-limited thematic challenges with community voting</p>
            </div>
            <div className="feature-item text-center hover-lift cursor-pointer" onClick={() => navigateTo('proofs')}>
              <div className="w-10 h-10 rounded-lg bg-costar-gray-dark flex items-center justify-center mb-3 mx-auto">
                <Shield size={20} />
              </div>
              <h3 className="feature-title">Proof of Creation</h3>
              <p className="feature-description mt-1">Blockchain-based timestamp proof for your creative work</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Login Page with CoStar styling
function LoginPage({ onBack, magicSDK, setUser, navigateTo }) {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [isArtist, setIsArtist] = useState(false);

  const handleMagicLogin = async (e) => {
    e.preventDefault();
    
    if (!email) {
      setError('Please enter your email');
      return;
    }
    
    setIsLoading(true);
    setError('');
    
    try {
      if (!magicSDK) {
        throw new Error('Authentication system not initialized');
      }
      
      await magicSDK.auth.loginWithMagicLink({ email });
      const didToken = await magicSDK.user.getIdToken();
      
      const response = await fetch('http://localhost:5001/api/magic/auth', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          didToken,
          username: username || undefined,
          isArtist
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        localStorage.setItem('token', data.data.token);
        const userData = { ...data.data.user, token: data.data.token };
        setUser(userData);
        navigateTo('home');
      } else {
        throw new Error(data.message || 'Authentication failed');
      }
    } catch (error) {
      console.error('Login error:', error);
      setError(error.message || 'Failed to login. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTraditionalLogin = async (e) => {
    e.preventDefault();
    
    if (!email || !password) {
      setError('Please enter both email and password');
      return;
    }
    
    setIsLoading(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:5001/api/users/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email, password })
      });
      
      const data = await response.json();
      
      if (data.success) {
        localStorage.setItem('token', data.data.token);
        const userData = { ...data.data.user, token: data.data.token };
        setUser(userData);
        navigateTo('home');
      } else {
        throw new Error(data.message || 'Authentication failed');
      }
    } catch (error) {
      console.error('Login error:', error);
      setError(error.message || 'Failed to login. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleSignUp = async (e) => {
    e.preventDefault();
    
    if (!email || !username || !password) {
      setError('Please fill all required fields');
      return;
    }
    
    setIsLoading(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:5001/api/users/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          email, 
          username, 
          password,
          isArtist
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        localStorage.setItem('token', data.data.token);
        const userData = { ...data.data.user, token: data.data.token };
        setUser(userData);
        navigateTo('home');
      } else {
        throw new Error(data.message || 'Registration failed');
      }
    } catch (error) {
      console.error('Signup error:', error);
      setError(error.message || 'Failed to sign up. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-80px)] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-hero mb-2">
            {isSignUp ? "Join REBEL" : "Welcome back"}
          </h1>
          <p className="text-costar-text-muted">
            {isSignUp 
              ? "Create your account to start sharing music" 
              : "Sign in to continue your journey"
            }
          </p>
        </div>
        
        <div className="costar-card">
          {error && (
            <div className="error-costar mb-4">
              {error}
            </div>
          )}

          {isSignUp ? (
            <form onSubmit={handleSignUp}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="input-costar"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Username</label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="input-costar"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input-costar"
                    required
                  />
                </div>
                <div className="flex items-center">
                  <input 
                    type="checkbox" 
                    checked={isArtist}
                    onChange={(e) => setIsArtist(e.target.checked)}
                    className="w-4 h-4 mr-3"
                  />
                  <span className="text-sm">Sign up as an artist</span>
                </div>
              </div>
              <div className="mt-6 space-y-3">
                <button 
                  type="submit"
                  disabled={isLoading}
                  className="w-full btn-primary-costar"
                >
                  {isLoading ? 'Creating Account...' : 'Sign Up'}
                </button>
                <div className="text-center text-xs text-costar-text-muted">OR</div>
                <button 
                  type="button" 
                  onClick={handleMagicLogin}
                  disabled={isLoading}
                  className="w-full btn-secondary-costar"
                >
                  {isLoading ? 'Processing...' : 'Sign Up with Magic Link'}
                </button>
              </div>
            </form>
          ) : (
            <div>
              <div className="mb-6">
                <button 
                  onClick={handleMagicLogin}
                  disabled={isLoading}
                  className="w-full btn-primary-costar flex items-center justify-center space-x-2"
                >
                  <LogIn size={20} />
                  <span>{isLoading ? 'Connecting...' : 'Login with Magic Link'}</span>
                </button>
              </div>
              
              <div className="relative mb-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-costar-border"></div>
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="px-2 bg-costar-card text-costar-text-muted">Or login with email/password</span>
                </div>
              </div>
              
              <form onSubmit={handleTraditionalLogin}>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium mb-2">Email</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="input-costar"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">Password</label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="input-costar"
                      required
                    />
                  </div>
                </div>
                <button 
                  type="submit"
                  disabled={isLoading}
                  className="w-full btn-secondary-costar mt-6"
                >
                  {isLoading ? 'Logging In...' : 'Login'}
                </button>
              </form>
            </div>
          )}
          
          <div className="mt-6 text-center">
            <button
              onClick={() => setIsSignUp(!isSignUp)}
              className="text-sm text-white hover:opacity-80 transition-opacity"
            >
              {isSignUp 
                ? "Already have an account? Sign in" 
                : "Need an account? Sign up"
              }
            </button>
          </div>
          
          <div className="mt-6 text-center">
            <button
              onClick={onBack}
              className="text-sm text-costar-text-muted hover:text-white transition-colors"
            >
              ← Back to Home
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Profile Page
function ProfilePage({ user, setUser, onBack }) {
  const [formData, setFormData] = useState({
    username: user?.username || '',
    email: user?.email || '',
    bio: user?.bio || '',
    location: user?.location || '',
    website: user?.website || '',
    isArtist: user?.isArtist || false
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [profilePicture, setProfilePicture] = useState(null);
  const [walletInfo, setWalletInfo] = useState(null);
  const [walletLoading, setWalletLoading] = useState(false);

  useEffect(() => {
    fetchWalletInfo();
  }, []);

  const fetchWalletInfo = async () => {
    if (!user?.token) return;
    
    setWalletLoading(true);
    try {
      const response = await fetch('http://localhost:5001/api/magic/wallet', {
        headers: {
          'Authorization': `Bearer ${user.token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setWalletInfo(data.data);
        }
      }
    } catch (error) {
      console.error('Error fetching wallet info:', error);
    } finally {
      setWalletLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleFileChange = (e) => {
    setProfilePicture(e.target.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    setSuccess('');
    
    try {
      const formDataObj = new FormData();
      Object.entries(formData).forEach(([key, value]) => {
        formDataObj.append(key, value);
      });
      
      if (profilePicture) {
        formDataObj.append('profilePicture', profilePicture);
      }
      
      const response = await fetch('http://localhost:5001/api/users/profile', {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${user.token}`
        },
        body: formDataObj
      });
      
      const data = await response.json();
      
      if (data.success) {
        setSuccess('Profile updated successfully');
        setUser(prev => ({
          ...prev,
          ...data.data
        }));
      } else {
        throw new Error(data.message || 'Failed to update profile');
      }
    } catch (error) {
      console.error('Profile update error:', error);
      setError(error.message || 'Failed to update profile. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const becomeArtist = async () => {
    setIsLoading(true);
    setError('');
    setSuccess('');
    
    try {
      const response = await fetch('http://localhost:5001/api/users/become-artist', {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${user.token}`,
          'Content-Type': 'application/json'
        }
      });
      
      const data = await response.json();
      
      if (data.success) {
        setSuccess('You are now registered as an artist!');
        setFormData(prev => ({ ...prev, isArtist: true }));
        setUser(prev => ({
          ...prev,
          isArtist: true
        }));
      } else {
        throw new Error(data.message || 'Failed to register as artist');
      }
    } catch (error) {
      console.error('Become artist error:', error);
      setError(error.message || 'Failed to register as artist. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="flex items-center mb-8">
        <button
          onClick={onBack}
          className="mr-4 p-2 rounded-lg bg-costar-card hover:bg-costar-gray-dark transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-hero">Your Profile</h1>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="costar-card">
            {error && (
              <div className="error-costar mb-4">
                {error}
              </div>
            )}
            
            {success && (
              <div className="success-costar mb-4">
                {success}
              </div>
            )}
            
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Profile Picture</label>
                <div className="flex items-center space-x-4">
                  <div className="w-16 h-16 rounded-full bg-costar-gray-dark flex items-center justify-center overflow-hidden">
                    {user.profilePicture ? (
                      <img 
                        src={`http://localhost:5001/uploads/profiles/${user.profilePicture}`}
                        alt={user.username}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <span className="text-xl font-bold">{user.username?.charAt(0).toUpperCase()}</span>
                    )}
                  </div>
                  <input
                    type="file"
                    onChange={handleFileChange}
                    className="text-sm text-costar-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-white file:text-black hover:file:bg-gray-100"
                  />
                </div>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Username</label>
                  <input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    className="input-costar"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Email</label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    className="input-costar"
                    readOnly
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Bio</label>
                  <textarea
                    name="bio"
                    value={formData.bio}
                    onChange={handleChange}
                    className="input-costar h-32"
                  ></textarea>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Location</label>
                  <input
                    type="text"
                    name="location"
                    value={formData.location}
                    onChange={handleChange}
                    className="input-costar"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Website</label>
                  <input
                    type="url"
                    name="website"
                    value={formData.website}
                    onChange={handleChange}
                    className="input-costar"
                  />
                </div>
              </div>
              <div className="flex space-x-4 mt-6">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="btn-primary-costar"
                >
                  {isLoading ? 'Saving...' : 'Save Changes'}
                </button>
                <button
                  type="button"
                  onClick={onBack}
                  className="btn-secondary-costar"
                >
                  Back
                </button>
              </div>
            </form>
          </div>
          
          {!formData.isArtist && (
            <div className="costar-card mt-6">
              <h2 className="text-section-title mb-4">Become an Artist</h2>
              <p className="text-costar-text-muted mb-4">
                Register as an artist to upload tracks and create timestamps proofs of your works.
              </p>
              <button
                onClick={becomeArtist}
                disabled={isLoading}
                className="btn-primary-costar"
              >
                {isLoading ? 'Processing...' : 'Register as Artist'}
              </button>
            </div>
          )}
        </div>
        
        <div>
          <div className="costar-card mb-6">
            <h2 className="text-section-title mb-4">Wallet Information</h2>
            {walletLoading ? (
              <div className="flex justify-center py-4">
                <div className="loading-costar"></div>
              </div>
            ) : walletInfo ? (
              <div>
                <div className="mb-4">
                  <h3 className="text-sm text-costar-text-muted">Solana Address</h3>
                  <p className="text-xs font-mono bg-costar-gray-dark p-2 rounded mt-1 break-all">
                    {walletInfo.solanaAddress}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm text-costar-text-muted">Balance</h3>
                  <p className="text-lg font-medium mt-1">{walletInfo.balance} SOL</p>
                </div>
              </div>
            ) : (
              <p className="text-costar-text-muted">No wallet information available.</p>
            )}
          </div>
          
          <div className="costar-card">
            <h2 className="text-section-title mb-4">Account Status</h2>
            <div className="space-y-3">
              <div>
                <h3 className="text-sm text-costar-text-muted">Account Type</h3>
                <p className="font-medium">
                  {formData.isArtist ? (
                    <span className="text-white">Artist</span>
                  ) : (
                    <span>Regular User</span>
                  )}
                </p>
              </div>
              <div>
                <h3 className="text-sm text-costar-text-muted">Member Since</h3>
                <p className="font-medium">
                  {user.createdAt ? new Date(user.createdAt).toLocaleDateString() : 'N/A'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Tracks Page
function TracksPage({ user, onBack, navigateTo }) {
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchTracks();
  }, []);

  const fetchTracks = async () => {
    try {
      const response = await fetch('http://localhost:5001/api/tracks/user', {
        headers: {
          'Authorization': `Bearer ${user.token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setTracks(Array.isArray(data.data) ? data.data : data.data.tracks || []);
        } else {
          setError(data.message || 'Failed to fetch tracks');
        }
      } else {
        setError('Failed to fetch tracks');
      }
    } catch (error) {
      console.error('Error fetching tracks:', error);
      setError(error.message || 'Failed to fetch tracks');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <div className="flex justify-between items-center mb-8">
        <div className="flex items-center">
          <button
            onClick={onBack}
            className="mr-4 p-2 rounded-lg bg-costar-card hover:bg-costar-gray-dark transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-hero">My Tracks</h1>
        </div>
        <button
          onClick={() => navigateTo('upload')}
          className="btn-primary-costar flex items-center space-x-2"
        >
          <Upload size={18} />
          <span>Upload New Track</span>
        </button>
      </div>
      
      {error && (
        <div className="error-costar mb-4">
          {error}
        </div>
      )}
      
      {success && (
        <div className="success-costar mb-4">
          {success}
        </div>
      )}
      
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="loading-costar"></div>
        </div>
      ) : tracks.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {tracks.map(track => (
            <div key={track._id} className="costar-card hover-lift">
              <div className="flex items-start">
                <div className="w-12 h-12 rounded-lg bg-costar-gray-dark flex items-center justify-center mr-4">
                  <Music size={20} />
                </div>
                <div className="flex-1">
                  <h3 className="text-card-title">{track.title}</h3>
                  <p className="text-costar-text-muted text-sm">
                    {track.genre} • {Math.floor(track.duration / 60)}:{(track.duration % 60).toString().padStart(2, '0')}
                  </p>
                  <p className="text-costar-text-muted text-small mt-1">
                    Uploaded {new Date(track.createdAt).toLocaleDateString()}
                  </p>
                </div>
              </div>
              
              {track.description && (
                <p className="text-costar-text-muted mt-3 text-sm">{track.description}</p>
              )}
              
              <div className="mt-4 flex flex-wrap gap-2">
                {track.tags && track.tags.map(tag => (
                  <span key={tag} className="bg-costar-gray-dark text-costar-text-muted px-2 py-1 rounded text-xs">
                    {tag}
                  </span>
                ))}
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-center text-costar-text-muted text-sm">
                  <span className="mr-4">{track.plays || 0} plays</span>
                </div>
                
                <div className="flex space-x-2">
                  <a 
                    href={`http://localhost:5001/uploads/tracks/${track.audioFile}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost-costar text-xs"
                  >
                    Play
                  </a>
                  <TrackProofButton 
                    trackId={track._id}
                    user={user}
                    onSuccess={(proofData) => {
                      setSuccess(`Proof created successfully for track: ${track._id}`);
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="costar-card text-center py-12">
          <Music size={48} className="text-costar-text-muted mx-auto mb-4" />
          <h3 className="text-section-title mb-2">No tracks yet</h3>
          <p className="text-costar-text-muted mb-6">
            You haven't uploaded any tracks yet. Upload your first track to get started.
          </p>
          <button
            onClick={() => navigateTo('upload')}
            className="btn-primary-costar inline-flex items-center space-x-2"
          >
            <Upload size={18} />
            <span>Upload First Track</span>
          </button>
        </div>
      )}
    </div>
  );
}

// Upload Page
function UploadPage({ user, onBack }) {
  const [formData, setFormData] = useState({
    title: '',
    genre: '',
    description: '',
    tags: '',
    isPublic: true
  });
  const [audioFile, setAudioFile] = useState(null);
  const [coverImage, setCoverImage] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (!user.isArtist) {
      setError('You need to be registered as an artist to upload tracks.');
    }
  }, [user.isArtist]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleAudioFileChange = (e) => {
    setAudioFile(e.target.files[0]);
  };

  const handleCoverImageChange = (e) => {
    setCoverImage(e.target.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!audioFile) {
      setError('Please select an audio file');
      return;
    }
    
    setIsLoading(true);
    setError('');
    setSuccess('');
    
    try {
      const uploadData = new FormData();
      uploadData.append('title', formData.title);
      uploadData.append('genre', formData.genre);
      uploadData.append('description', formData.description);
      uploadData.append('isPublic', formData.isPublic);
      
      if (formData.tags) {
        const tagsArray = formData.tags.split(',').map(tag => tag.trim());
        uploadData.append('tags', tagsArray.join(','));
      }
      
      uploadData.append('audioFile', audioFile);
      
      if (coverImage) {
        uploadData.append('coverImage', coverImage);
      }
      
      const response = await fetch('http://localhost:5001/api/tracks', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user.token}`
        },
        body: uploadData
      });
      
      const data = await response.json();
      
      if (data.success) {
        setSuccess('Track uploaded successfully!');
        setFormData({
          title: '',
          genre: '',
          description: '',
          tags: '',
          isPublic: true
        });
        setAudioFile(null);
        setCoverImage(null);
      } else {
        throw new Error(data.message || 'Failed to upload track');
      }
    } catch (error) {
      console.error('Upload error:', error);
      setError(error.message || 'Failed to upload track. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <div className="flex items-center mb-8">
        <button
          onClick={onBack}
          className="mr-4 p-2 rounded-lg bg-costar-card hover:bg-costar-gray-dark transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-hero">Upload Track</h1>
      </div>
      
      <div className="costar-card">
        {error && (
          <div className="error-costar mb-4">
            {error}
          </div>
        )}
        
        {success && (
          <div className="success-costar mb-4">
            {success}
          </div>
        )}
        
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Title *</label>
              <input
                type="text"
                name="title"
                value={formData.title}
                onChange={handleChange}
                className="input-costar"
                required
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Genre *</label>
              <input
                type="text"
                name="genre"
                value={formData.genre}
                onChange={handleChange}
                className="input-costar"
                required
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Description</label>
              <textarea
                name="description"
                value={formData.description}
                onChange={handleChange}
                className="input-costar h-32"
              ></textarea>
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Tags (comma separated)</label>
              <input
                type="text"
                name="tags"
                value={formData.tags}
                onChange={handleChange}
                placeholder="electronic, ambient, experimental"
                className="input-costar"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Audio File *</label>
              <input
                type="file"
                accept="audio/*"
                onChange={handleAudioFileChange}
                className="text-sm text-costar-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-white file:text-black hover:file:bg-gray-100"
                required
              />
              <p className="mt-1 text-xs text-costar-text-muted">
                Supported formats: MP3, WAV, FLAC, OGG (max 30MB)
              </p>
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Cover Image (optional)</label>
              <input
                type="file"
                accept="image/*"
                onChange={handleCoverImageChange}
                className="text-sm text-costar-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-white file:text-black hover:file:bg-gray-100"
              />
              <p className="mt-1 text-xs text-costar-text-muted">
                Recommended: 800x800 JPG or PNG (max 2MB)
              </p>
            </div>
            
            <div className="flex items-center">
              <input 
                type="checkbox"
                name="isPublic"
                checked={formData.isPublic}
                onChange={handleChange}
                className="w-4 h-4 mr-3"
              />
              <span className="text-sm">Make this track public</span>
            </div>
          </div>
          
          <div className="flex space-x-4 mt-8">
            <button
              type="submit"
              disabled={isLoading || !user.isArtist}
              className="btn-primary-costar"
            >
              {isLoading ? 'Uploading...' : 'Upload Track'}
            </button>
            <button
              type="button"
              onClick={onBack}
              className="btn-secondary-costar"
            >
              Back
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Proofs Page
function ProofsPage({ user, onBack }) {
  const [proofs, setProofs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [selectedProof, setSelectedProof] = useState(null);
  const [verificationFile, setVerificationFile] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [showVerifyModal, setShowVerifyModal] = useState(false);

  useEffect(() => {
    fetchProofs();
  }, []);

  const fetchProofs = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:5001/api/proofs/user/me', {
        headers: {
          'Authorization': `Bearer ${user.token}`
        }
      });
      
      const data = await response.json();
      
      if (data.success) {
        setProofs(data.data.proofs || []);
      } else {
        setError(data.message || 'Failed to fetch proofs');
      }
    } catch (error) {
      console.error('Error fetching proofs:', error);
      setError(error.message || 'Failed to fetch proofs');
    } finally {
      setLoading(false);
    }
  };

  const payForProof = async (proofId) => {
    try {
      setLoading(true);
      setError('');
      setSuccess('');

      const response = await fetch(`http://localhost:5001/api/proofs/pay/${proofId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user.token}`,
          'Content-Type': 'application/json'
        }
      });
      
      const data = await response.json();
      
      if (data.success) {
        setSuccess('Payment successful! Your proof is being processed.');
        fetchProofs();
      } else {
        setError(data.message || 'Payment failed');
      }
    } catch (error) {
      console.error('Payment error:', error);
      setError(error.message || 'Payment failed');
    } finally {
      setLoading(false);
    }
  };

  const downloadProof = async (proofId) => {
    try {
      setLoading(true);
      setError('');

      const response = await fetch(`http://localhost:5001/api/proofs/download/${proofId}`, {
        headers: {
          'Authorization': `Bearer ${user.token}`
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Failed to download proof');
      }
      
      const result = await response.json();
      
      if (result.success) {
        const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = result.filename || `proof_${proofId}.json`;
        document.body.appendChild(a);
        a.click();
        
        URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        setSuccess('Proof downloaded successfully');
      } else {
        throw new Error(result.message || 'Failed to download proof');
      }
    } catch (error) {
      console.error('Download error:', error);
      setError(error.message || 'Failed to download proof');
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'CONFIRMED':
        return 'text-green-300 bg-green-900 bg-opacity-20';
      case 'PENDING':
        return 'text-yellow-300 bg-yellow-900 bg-opacity-20';
      case 'FAILED':
      case 'REJECTED':
        return 'text-red-300 bg-red-900 bg-opacity-20';
      default:
        return 'text-costar-text-muted bg-costar-gray-dark';
    }
  };

  const formatDate = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <div className="flex items-center mb-8">
        <button
          onClick={onBack}
          className="mr-4 p-3 rounded-lg bg-costar-card hover:bg-costar-gray-dark transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div>
          <h1 className="text-hero">Proof of Creation</h1>
          <p className="text-costar-text-muted">Manage your blockchain timestamp proofs</p>
        </div>
      </div>

      {error && (
        <div className="error-costar mb-6 flex items-start">
          <AlertTriangle size={20} className="mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <p>{error}</p>
            <button
              onClick={() => setError('')}
              className="text-xs mt-1 hover:text-white transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
      
      {success && (
        <div className="success-costar mb-6 flex items-start">
          <CheckCircle size={20} className="mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <p>{success}</p>
            <button
              onClick={() => setSuccess('')}
              className="text-xs mt-1 hover:text-white transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="loading-costar"></div>
        </div>
      ) : proofs.length > 0 ? (
        <div className="space-y-4">
          {proofs.map(proof => (
            <div key={proof._id} className="costar-card hover-lift">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between">
                <div className="flex items-center mb-4 lg:mb-0">
                  <div className="bg-costar-gray-dark rounded-lg p-3 mr-4">
                    <Shield size={24} />
                  </div>
                  <div>
                    <h2 className="text-card-title">{proof.title}</h2>
                    <div className="flex items-center mt-1 text-sm text-costar-text-muted">
                      <span>Created: {formatDate(proof.createdAt)}</span>
                      <span className="mx-2">•</span>
                      <span>Version {proof.version}</span>
                      <span className="mx-2">•</span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(
                          proof.status
                        )}`}
                      >
                        {proof.status}
                      </span>
                    </div>
                  </div>
                </div>
                
                <div className="flex flex-wrap gap-2">
                  {proof.status === 'CONFIRMED' && proof.payment?.isPaid && (
                    <button
                      onClick={() => downloadProof(proof._id)}
                      className="btn-primary-costar flex items-center space-x-2 text-xs"
                    >
                      <Download size={16} />
                      <span>Download Proof</span>
                    </button>
                  )}
                  
                  {proof.blockchain?.transactionId && (
                    <a
                      href={`https://explorer.solana.com/tx/${proof.blockchain.transactionId}?cluster=${proof.blockchain.network || 'devnet'}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary-costar flex items-center space-x-2 text-xs"
                    >
                      <ExternalLink size={16} />
                      <span>View on Explorer</span>
                    </a>
                  )}
                  
                  {!proof.payment?.isPaid && (
                    <button
                      onClick={() => payForProof(proof._id)}
                      className="btn-primary-costar text-xs"
                    >
                      Pay {proof.payment?.cost || 10} RP
                    </button>
                  )}
                </div>
              </div>
              
              <div className="mt-4">
                <div className="text-sm text-costar-text-muted mb-1">Content Hash</div>
                <div className="bg-costar-gray-dark p-3 rounded text-xs font-mono overflow-x-auto">
                  {proof.contentHash}
                </div>
              </div>
              
              {proof.blockchain?.pdaAddress && (
                <div className="mt-4">
                  <div className="text-sm text-costar-text-muted mb-1">Blockchain Address</div>
                  <div className="bg-costar-gray-dark p-3 rounded text-xs font-mono overflow-x-auto">
                    {proof.blockchain.pdaAddress}
                  </div>
                </div>
              )}
              
              {proof.status === 'PENDING' && proof.payment?.isPaid && (
                <div className="mt-4 flex items-center text-yellow-300 text-sm">
                  <Clock size={16} className="mr-2" />
                  Your proof is being processed on the blockchain...
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="costar-card text-center py-12">
          <div className="bg-costar-gray-dark rounded-full p-4 inline-flex mb-4">
            <Shield size={40} />
          </div>
          <h2 className="text-section-title mb-2">No Proofs Yet</h2>
          <p className="text-costar-text-muted mb-6">
            You haven't created any proofs of creation for your tracks yet.
          </p>
          <button
            onClick={() => window.location.href = '/tracks'}
            className="btn-primary-costar"
          >
            Create Your First Proof
          </button>
        </div>
      )}
    </div>
  );
}



// Help Page
function HelpPage({ onBack }) {
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="flex items-center mb-8">
        <button
          onClick={onBack}
          className="mr-4 p-2 rounded-lg bg-costar-card hover:bg-costar-gray-dark transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-hero">About REBEL</h1>
      </div>
      
      <div className="space-y-6">
        <div className="costar-card">
          <h2 className="text-section-title mb-4">Our Vision</h2>
          <p className="text-costar-text-muted mb-4">
            REBEL is the definitive anti-algorithmic sanctuary for underground music, 
            where human curation trumps AI recommendations, restoring cultural value and 
            financial sustainability to authentic electronic and experimental music scenes.
          </p>
          <p className="text-costar-text-muted">
            We rebuild the discovery-to-monetization pipeline through a decentralized ecosystem 
            where fans, DJs, and micro-labels connect directly, underpinned by transparent Web3 
            infrastructure that rewards genuine cultural contribution rather than algorithmic metrics.
          </p>
        </div>
        
        <div className="costar-card">
          <h2 className="text-section-title mb-4">The Problem</h2>
          <ul className="list-disc pl-5 text-costar-text-muted space-y-2 mb-4">
            <li>90% of music industry revenues are distributed to only 2% of artists</li>
            <li>Algorithmic platforms create a discovery barrier for niche/underground artists</li>
            <li>Homogenization of music due to algorithm-based recommendations (-30% sonic diversity)</li>
            <li>60-70% of streaming consumption driven by algorithmic recommendations</li>
            <li>AI-generated music threatens authentic human creation</li>
          </ul>
        </div>
        
        <div className="costar-card">
          <h2 className="text-section-title mb-4">Core Features</h2>
          <div className="space-y-4">
            <div>
              <h3 className="text-white font-medium mb-1">Sonic Map</h3>
              <p className="text-costar-text-muted">Visual interface representing music by sonic characteristics (texture, energy, experimentation) rather than popularity metrics.</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">P2P Sharing System</h3>
              <p className="text-costar-text-muted">Decentralized exchange for rare/exclusive tracks with provenance verification and fair-value pricing determined by community.</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Live Crates/Sonic Vaults</h3>
              <p className="text-costar-text-muted">Time-limited thematic challenges with community voting system and rewards for curation and discovery contributions.</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Proof of Creation</h3>
              <p className="text-costar-text-muted">Blockchain-based timestamp proofs that protect your work with verifiable evidence of creation time and ownership.</p>
            </div>
          </div>
        </div>
        
        <div className="costar-card">
          <h2 className="text-section-title mb-4">How to Use REBEL</h2>
          <div className="space-y-4">
            <div>
              <h3 className="text-white font-medium mb-1">Registration</h3>
              <p className="text-costar-text-muted">Sign up using Magic Link for passwordless authentication, or use traditional email/password. Artists need to register as artists to upload tracks.</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Uploading Tracks</h3>
              <p className="text-costar-text-muted">Once registered as an artist, you can upload tracks with metadata including title, genre, description, and tags.</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Creating Proofs</h3>
              <p className="text-costar-text-muted">After uploading a track, you can create a blockchain timestamp proof. The first proof for each track is free, subsequent proofs cost Rebellion Points (RP).</p>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Account Abstraction</h3>
              <p className="text-costar-text-muted">Our Web3 infrastructure is invisible to you - we handle all the blockchain interactions while providing the benefits of decentralization.</p>
            </div>
          </div>
        </div>
        
        <button
          onClick={onBack}
          className="btn-primary-costar"
        >
          Back to Home
        </button>
      </div>
    </div>
  );
}

export default App;