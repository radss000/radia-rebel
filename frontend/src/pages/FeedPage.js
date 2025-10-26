import React, { useState, useEffect } from 'react';
import { Music, Calendar, MapPin, Clock, Heart, MessageCircle, Share, Camera, Image as ImageIcon, Gift, Headphones, Star, Zap } from 'lucide-react';

function FeedPage({ user, navigateTo }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newPost, setNewPost] = useState('');
  const [showComposer, setShowComposer] = useState(false);
  
  // Génère un avatar avec initiales et couleur basée sur le nom d'utilisateur
  const generateAvatar = (username) => {
    const colors = [
      'bg-violet-500', 'bg-blue-500', 'bg-green-500', 'bg-purple-500', 
      'bg-yellow-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
      'bg-red-500', 'bg-orange-500', 'bg-cyan-500', 'bg-emerald-500'
    ];
    const color = colors[username.charCodeAt(0) % colors.length];
    const initials = username.slice(0, 2).toUpperCase();
    
    return (
      <div className={`w-full h-full ${color} rounded-full flex items-center justify-center text-white font-semibold text-sm`}>
        {initials}
      </div>
    );
  };
  
  // Fonction pour afficher l'avatar ou l'image de profil
  const renderProfilePicture = (user, size = "w-10 h-10") => {
    return (
      <div className={`${size} rounded-full overflow-hidden bg-costar-gray-dark flex items-center justify-center`}>
        {user.profilePicture ? (
          <img 
            src={`http://localhost:5001/uploads/profiles/${user.profilePicture}`}
            alt={user.username}
            className="w-full h-full object-cover"
          />
        ) : (
          generateAvatar(user.username)
        )}
      </div>
    );
  };
  
  useEffect(() => {
    loadStaticFeed();
  }, []);
  
  const loadStaticFeed = () => {
    const staticFeed = [
      {
        id: 'post1',
        type: 'track',
        user: {
          id: 'user1',
          username: 'JazzMaster42',
          profilePicture: null,
          isArtist: true
        },
        content: {
          title: 'Autumn Leaves Reinterpretation',
          caption: 'Hey everyone! Here\'s a snippet of the intro to my upcoming album. Would love your feedback!',
          audioFile: 'sample-track-1.mp3',
          genre: 'Future Jazz',
          price: 2.5,
          coverImage: null // Pas d'image pour tester l'icône
        },
        likes: 42,
        comments: [
          {
            id: 'comment1',
            user: {
              id: 'user2',
              username: 'FutureBeatsLover',
              profilePicture: null
            },
            text: 'This is amazing! Can\'t wait for the full album release!',
            timestamp: new Date('2025-05-01T12:30:00.000Z')
          }
        ],
        timestamp: new Date('2025-05-01T10:15:00.000Z')
      },
      {
        id: 'post2',
        type: 'event',
        user: {
          id: 'user3',
          username: 'DPitchRecords',
          profilePicture: null,
          isLabel: true
        },
        content: {
          title: 'DPitch Showcase Paris',
          description: 'Join us for an unforgettable night of underground electronic music at La Machine du Moulin Rouge. Featuring our top artists and special guests!',
          date: 'May 19, 2025',
          location: 'Paris, France',
          coverImage: 'https://s11.aconvert.com/convert/p3r68-cdx67/ebo4a-vhc7i.jpeg'
        },
        likes: 118,
        comments: [
          {
            id: 'comment2',
            user: {
              id: 'user4',
              username: 'TechnoEnthusiast',
              profilePicture: null
            },
            text: 'Will be there for sure! Last event was incredible.',
            timestamp: new Date('2025-05-02T09:45:00.000Z')
          }
        ],
        timestamp: new Date('2025-05-02T08:30:00.000Z')
      },
      {
        id: 'post3',
        type: 'challenge',
        user: {
          id: 'user5',
          username: 'REBEL_Admin',
          profilePicture: null,
          isAdmin: true
        },
        content: {
          title: 'Francesco Del Garda Challenge',
          description: 'Find the curated playlist on the sonic map from the legendary digger Francesco Del Garda and win exclusive benefits!',
          deadline: 'May 10, 2025',
          prizes: ['Exclusive track downloads', 'REBEL Points', 'Early access to new features']
        },
        likes: 87,
        comments: [
          {
            id: 'comment3',
            user: {
              id: 'user6',
              username: 'DiggerQueen',
              profilePicture: null
            },
            text: 'Challenge accepted! His taste in music is unparalleled.',
            timestamp: new Date('2025-05-02T14:20:00.000Z')
          }
        ],
        timestamp: new Date('2025-05-02T13:00:00.000Z')
      }
    ];
    
    setPosts(staticFeed);
    setLoading(false);
  };
  
  const handleLike = (postId) => {
    setPosts(prevPosts => 
      prevPosts.map(post => 
        post.id === postId 
          ? { ...post, likes: post.likes + 1 } 
          : post
      )
    );
  };
  
  const handleComment = (postId, comment) => {
    const newComment = {
      id: `comment${Date.now()}`,
      user: {
        id: user.id,
        username: user.username,
        profilePicture: user.profilePicture
      },
      text: comment,
      timestamp: new Date()
    };
    
    setPosts(prevPosts => 
      prevPosts.map(post => 
        post.id === postId 
          ? { 
              ...post, 
              comments: [...post.comments, newComment] 
            } 
          : post
      )
    );
  };
  
  const handleBuy = (postId) => {
    alert('Purchase functionality will be implemented soon!');
  };
  
  const handleCreatePost = () => {
    if (!newPost.trim()) return;
    
    const post = {
      id: `post${Date.now()}`,
      type: 'text',
      user: {
        id: user.id,
        username: user.username,
        profilePicture: user.profilePicture,
        isArtist: user.isArtist
      },
      content: {
        text: newPost
      },
      likes: 0,
      comments: [],
      timestamp: new Date()
    };
    
    setPosts(prevPosts => [post, ...prevPosts]);
    setNewPost('');
    setShowComposer(false);
  };
  
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-hero">REBEL Feed</h1>
      </div>
      
      {error && (
        <div className="error-costar mb-4">
          {error}
        </div>
      )}
      
      {/* Post Composer */}
      <div className="costar-card mb-6">
        <div className="flex items-center space-x-3">
          {renderProfilePicture(user)}
          <div className="flex-1">
            {showComposer ? (
              <div>
                <textarea
                  value={newPost}
                  onChange={(e) => setNewPost(e.target.value)}
                  placeholder="Share your thoughts..."
                  className="input-costar h-24 resize-none"
                />
                <div className="flex items-center justify-between mt-3">
                  <div className="flex space-x-2">
                    <button className="btn-ghost-costar text-xs">
                      <ImageIcon size={16} className="mr-1" />
                      Image
                    </button>
                    <button className="btn-ghost-costar text-xs">
                      <Music size={16} className="mr-1" />
                      Track
                    </button>
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => {
                        setShowComposer(false);
                        setNewPost('');
                      }}
                      className="btn-secondary-costar text-xs"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreatePost}
                      disabled={!newPost.trim()}
                      className="btn-primary-costar text-xs"
                    >
                      Post
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowComposer(true)}
                className="w-full text-left input-costar text-costar-text-muted"
              >
                What's on your mind, {user.username}?
              </button>
            )}
          </div>
        </div>
      </div>
      
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="loading-costar"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {posts.map(post => (
            <div key={post.id} className="costar-card">
              {/* Post Header */}
              <div className="border-b border-costar-border pb-4 mb-4">
                <div className="flex items-center">
                  {renderProfilePicture(post.user)}
                  <div className="ml-3">
                    <div className="font-medium flex items-center">
                      {post.user.username}
                      {post.user.isArtist && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-white bg-opacity-10 rounded-full">Artist</span>
                      )}
                      {post.user.isLabel && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-blue-900 bg-opacity-20 text-blue-300 rounded-full">Label</span>
                      )}
                      {post.user.isAdmin && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-red-900 bg-opacity-20 text-red-300 rounded-full">Admin</span>
                      )}
                    </div>
                    <div className="text-xs text-costar-text-muted">
                      {new Date(post.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Post Content */}
              <div>
                {post.type === 'text' && (
                  <div>
                    <p className="text-costar-text-light">{post.content.text}</p>
                  </div>
                )}
                
                {post.type === 'track' && (
                  <div>
                    <h3 className="text-section-title mb-2">{post.content.title}</h3>
                    <p className="text-costar-text-muted mb-4">{post.content.caption}</p>
                    <div className="bg-costar-gray-dark rounded-lg overflow-hidden mb-4">
                      <div className="flex items-center p-3">
                        <div className="w-16 h-16 bg-costar-gray-light rounded-md flex-shrink-0 flex items-center justify-center mr-3">
                          {post.content.coverImage ? (
                            <img 
                              src={`http://localhost:5001/uploads/covers/${post.content.coverImage}`}
                              alt={post.content.title}
                              className="w-full h-full object-cover rounded-md"
                            />
                          ) : (
                            <Music size={32} className="text-costar-text-muted" />
                          )}
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-costar-text-muted mb-1">{post.content.genre}</p>
                          <audio 
                            controls 
                            className="w-full"
                            src={`http://localhost:5001/uploads/tracks/${post.content.audioFile}`}
                          ></audio>
                        </div>
                      </div>
                      <div className="flex justify-between items-center p-3 border-t border-costar-border">
                        <span className="text-costar-text-muted">Price: {post.content.price} SOL</span>
                        <button 
                          onClick={() => handleBuy(post.id)} 
                          className="btn-primary-costar text-xs"
                        >
                          Buy Now
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                
                {post.type === 'event' && (
                  <div>
                    <h3 className="text-section-title mb-2">{post.content.title}</h3>
                    <p className="text-costar-text-muted mb-4">{post.content.description}</p>
                    <div className="bg-costar-gray-dark rounded-lg overflow-hidden mb-4">
                      {post.content.coverImage && (
                        <img 
                          src={post.content.coverImage}
                          alt={post.content.title}
                          className="w-full h-48 object-cover"
                        />
                      )}
                      <div className="p-4">
                        <div className="flex items-center mb-2">
                          <Calendar size={16} className="mr-2" />
                          <span>{post.content.date}</span>
                        </div>
                        <div className="flex items-center">
                          <MapPin size={16} className="mr-2" />
                          <span>{post.content.location}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                
                {post.type === 'challenge' && (
                  <div>
                    <h3 className="text-section-title mb-2">{post.content.title}</h3>
                    <p className="text-costar-text-muted mb-4">{post.content.description}</p>
                    <div className="bg-costar-gray-dark rounded-lg p-4 mb-4">
                      <div className="flex items-center mb-3">
                        <Clock size={16} className="mr-2" />
                        <span>Deadline: {post.content.deadline}</span>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium mb-2">Prizes:</h4>
                        <ul className="list-disc pl-5 text-sm">
                          {post.content.prizes.map((prize, index) => (
                            <li key={index}>{prize}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Interactions */}
                <div className="flex items-center justify-between mt-4">
                  <div className="flex items-center space-x-4">
                    <button 
                      onClick={() => handleLike(post.id)}
                      className="flex items-center text-costar-text-muted hover:text-white transition-colors"
                    >
                      <Heart size={18} className="mr-1" />
                      <span>{post.likes}</span>
                    </button>
                    <div className="flex items-center text-costar-text-muted">
                      <MessageCircle size={18} className="mr-1" />
                      <span>{post.comments.length}</span>
                    </div>
                  </div>
                  <div>
                    <button className="text-costar-text-muted hover:text-white transition-colors">
                      <Share size={18} />
                    </button>
                  </div>
                </div>
              </div>
              
              {/* Comments */}
              {post.comments.length > 0 && (
                <div className="pt-4 border-t border-costar-border mt-4">
                  <h4 className="text-sm font-medium mb-2">Comments</h4>
                  <div className="space-y-3">
                    {post.comments.map(comment => (
                      <div key={comment.id} className="flex items-start">
                        {renderProfilePicture(comment.user, "w-8 h-8")}
                        <div className="flex-1 ml-2">
                          <div className="bg-costar-gray-dark rounded-lg p-2">
                            <span className="font-medium text-sm">{comment.user.username}</span>
                            <p className="text-sm">{comment.text}</p>
                          </div>
                          <div className="text-xs text-costar-text-muted mt-1">
                            {new Date(comment.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Add Comment */}
              <div className="pt-4 border-t border-costar-border mt-4">
                <div className="flex items-center">
                  {renderProfilePicture(user, "w-8 h-8")}
                  <input 
                    type="text" 
                    placeholder="Add a comment..." 
                    className="input-costar ml-2"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter' && e.target.value.trim()) {
                        handleComment(post.id, e.target.value);
                        e.target.value = '';
                      }
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default FeedPage;