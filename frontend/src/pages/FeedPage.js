import React, { useState, useEffect } from 'react';
import { Music, Calendar, MapPin, Clock, Heart, MessageCircle, Share, Image, Plus, X } from 'lucide-react';

function FeedPage({ user, navigateTo }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showPostCreator, setShowPostCreator] = useState(false);
  const [newPost, setNewPost] = useState({
    type: 'track',
    title: '',
    caption: '',
    genre: '',
    price: '',
    description: '',
    date: '',
    location: '',
    audioFile: null,
    coverImage: null
  });
  
  // Function to generate a realistic avatar URL using DiceBear API
  const generateAvatarUrl = (username, style = 'avataaars') => {
    return `https://api.dicebear.com/7.x/${style}/svg?seed=${encodeURIComponent(username)}&backgroundColor=transparent`;
  };

  // Function to generate a placeholder image URL
  const generatePlaceholderImage = (width, height, text = '') => {
    return `https://via.placeholder.com/${width}x${height}/2a2a2a/ffffff?text=${encodeURIComponent(text)}`;
  };
  
  useEffect(() => {
    // For now, we'll load static data since we haven't built the backend for this yet
    loadStaticFeed();
  }, []);
  
  const loadStaticFeed = () => {
    // Enhanced simulated static feed data with better profile pictures
    const staticFeed = [
      {
        id: 'post1',
        type: 'track',
        user: {
          id: 'user1',
          username: 'JazzMaster42',
          profilePicture: generateAvatarUrl('JazzMaster42', 'avataaars'),
          isArtist: true
        },
        content: {
          title: 'Autumn Leaves Reinterpretation',
          caption: 'Hey everyone! Here\'s a snippet of the intro to my upcoming album. Would love your feedback! This track blends traditional jazz harmony with modern production techniques.',
          audioFile: 'sample-track-1.mp3',
          genre: 'Future Jazz',
          price: 2.5, // In SOL
          coverImage: generatePlaceholderImage(300, 300, 'Album+Cover')
        },
        likes: 42,
        comments: [
          {
            id: 'comment1',
            user: {
              id: 'user2',
              username: 'FutureBeatsLover',
              profilePicture: generateAvatarUrl('FutureBeatsLover', 'personas')
            },
            text: 'This is amazing! Can\'t wait for the full album release! The fusion of old-school jazz with modern elements is incredible.',
            timestamp: new Date('2025-05-01T12:30:00.000Z')
          },
          {
            id: 'comment1b',
            user: {
              id: 'user8',
              username: 'VinylCollector',
              profilePicture: generateAvatarUrl('VinylCollector', 'initials')
            },
            text: 'Reminds me of the golden age of Blue Note Records but with a fresh twist. Amazing work!',
            timestamp: new Date('2025-05-01T13:15:00.000Z')
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
          profilePicture: generateAvatarUrl('DPitchRecords', 'identicon'),
          isLabel: true
        },
        content: {
          title: 'DPitch Showcase Paris',
          description: 'Join us for an unforgettable night of underground electronic music at La Machine du Moulin Rouge. Featuring our top artists and special guests from the Berlin underground scene!',
          date: 'May 19, 2025',
          location: 'Paris, France',
          coverImage: 'https://i.imgur.com/RfyrmIf.jpeg' // This will be your uploaded image
        },
        likes: 118,
        comments: [
          {
            id: 'comment2',
            user: {
              id: 'user4',
              username: 'TechnoEnthusiast',
              profilePicture: generateAvatarUrl('TechnoEnthusiast', 'avataaars')
            },
            text: 'Will be there for sure! Last event was incredible. The sound system at La Machine is perfect for this kind of music.',
            timestamp: new Date('2025-05-02T09:45:00.000Z')
          },
          {
            id: 'comment2b',
            user: {
              id: 'user9',
              username: 'ParisUnderground',
              profilePicture: generateAvatarUrl('ParisUnderground', 'micah')
            },
            text: 'DPitch always brings the best! Can\'t wait to see who the special guests are.',
            timestamp: new Date('2025-05-02T10:30:00.000Z')
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
          profilePicture: generateAvatarUrl('REBEL_Admin', 'bottts'),
          isAdmin: true
        },
        content: {
          title: 'Francesco Del Garda Challenge',
          description: 'Find the curated playlist on the sonic map from the legendary digger Francesco Del Garda and win exclusive benefits! This collection features rare gems from the Italian underground scene spanning three decades.',
          deadline: 'May 10, 2025',
          prizes: ['Exclusive track downloads', 'REBEL Points', 'Early access to new features', 'VIP access to next event']
        },
        likes: 87,
        comments: [
          {
            id: 'comment3',
            user: {
              id: 'user6',
              username: 'DiggerQueen',
              profilePicture: generateAvatarUrl('DiggerQueen', 'avataaars')
            },
            text: 'Challenge accepted! His taste in music is unparalleled. Those Italian obscure releases are pure gold.',
            timestamp: new Date('2025-05-02T14:20:00.000Z')
          },
          {
            id: 'comment3b',
            user: {
              id: 'user10',
              username: 'RecordHunter',
              profilePicture: generateAvatarUrl('RecordHunter', 'personas')
            },
            text: 'Been following Francesco for years. This is going to be intense! 🔥',
            timestamp: new Date('2025-05-02T15:45:00.000Z')
          }
        ],
        timestamp: new Date('2025-05-02T13:00:00.000Z')
      },
      {
        id: 'post4',
        type: 'track',
        user: {
          id: 'user7',
          username: 'AmbientSoul',
          profilePicture: generateAvatarUrl('AmbientSoul', 'initials'),
          isArtist: true
        },
        content: {
          title: 'Midnight Reflections',
          caption: 'Late night studio session resulted in this ambient piece. Perfect for deep listening sessions. Field recordings from my recent trip to Iceland.',
          audioFile: 'sample-track-2.mp3',
          genre: 'Ambient',
          price: 1.8,
          coverImage: generatePlaceholderImage(300, 300, 'Ambient+Art')
        },
        likes: 28,
        comments: [
          {
            id: 'comment4',
            user: {
              id: 'user11',
              username: 'IcelandicVibes',
              profilePicture: generateAvatarUrl('IcelandicVibes', 'micah')
            },
            text: 'Those field recordings are hauntingly beautiful. Takes me back to the northern lights.',
            timestamp: new Date('2025-05-03T08:30:00.000Z')
          }
        ],
        timestamp: new Date('2025-05-03T06:00:00.000Z')
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
    // In a real app, this would send the comment to the backend
    const newComment = {
      id: `comment${Date.now()}`,
      user: {
        id: user.id,
        username: user.username,
        profilePicture: user.profilePicture || generateAvatarUrl(user.username, 'avataaars')
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
    // In a real app, this would initiate a purchase transaction
    alert('Purchase functionality will be implemented soon!');
  };

  const handleCreatePost = () => {
    setShowPostCreator(!showPostCreator);
    // Reset form when closing
    if (showPostCreator) {
      setNewPost({
        type: 'track',
        title: '',
        caption: '',
        genre: '',
        price: '',
        description: '',
        date: '',
        location: '',
        audioFile: null,
        coverImage: null
      });
    }
  };

  const handlePostSubmit = (e) => {
    e.preventDefault();
    
    // Create new post object
    const newPostObj = {
      id: `post${Date.now()}`,
      type: newPost.type,
      user: {
        id: user.id,
        username: user.username,
        profilePicture: user.profilePicture || generateAvatarUrl(user.username, 'avataaars'),
        isArtist: user.isArtist || false
      },
      content: {},
      likes: 0,
      comments: [],
      timestamp: new Date()
    };

    // Set content based on post type
    if (newPost.type === 'track') {
      newPostObj.content = {
        title: newPost.title,
        caption: newPost.caption,
        genre: newPost.genre,
        price: parseFloat(newPost.price) || 0,
        audioFile: newPost.audioFile?.name || 'user-track.mp3',
        coverImage: newPost.coverImage ? URL.createObjectURL(newPost.coverImage) : generatePlaceholderImage(300, 300, 'User+Track')
      };
    } else if (newPost.type === 'event') {
      newPostObj.content = {
        title: newPost.title,
        description: newPost.description,
        date: newPost.date,
        location: newPost.location,
        coverImage: newPost.coverImage ? URL.createObjectURL(newPost.coverImage) : generatePlaceholderImage(800, 400, 'User+Event')
      };
    }

    // Add new post to the beginning of the posts array
    setPosts(prevPosts => [newPostObj, ...prevPosts]);
    
    // Reset form and close creator
    setNewPost({
      type: 'track',
      title: '',
      caption: '',
      genre: '',
      price: '',
      description: '',
      date: '',
      location: '',
      audioFile: null,
      coverImage: null
    });
    setShowPostCreator(false);
  };

  const handleFileChange = (field, file) => {
    setNewPost(prev => ({
      ...prev,
      [field]: file
    }));
  };
  
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 text-violet-500">REBEL Feed</h1>
      
      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      {/* Post Creation Section */}
      <div className="bg-gray-800 rounded-lg p-4 mb-6">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-full overflow-hidden bg-gray-700">
            <img 
              src={user.profilePicture || generateAvatarUrl(user.username, 'avataaars')}
              alt={user.username}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.target.src = generateAvatarUrl(user.username, 'initials');
              }}
            />
          </div>
          <button
            onClick={handleCreatePost}
            className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-300 text-left px-4 py-3 rounded-lg transition-colors"
          >
            What's on your mind, {user.username}?
          </button>
          <button
            onClick={handleCreatePost}
            className="bg-violet-600 hover:bg-violet-700 text-white p-3 rounded-lg transition-colors"
          >
            <Plus size={20} />
          </button>
        </div>

        {/* Expanded Post Creator */}
        {showPostCreator && (
          <div className="mt-4 border-t border-gray-700 pt-4">
            <form onSubmit={handlePostSubmit}>
              {/* Post Type Selection */}
              <div className="mb-4">
                <label className="block text-gray-300 mb-2">Post Type</label>
                <select
                  value={newPost.type}
                  onChange={(e) => setNewPost(prev => ({ ...prev, type: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                >
                  <option value="track">Music Track</option>
                  <option value="event">Event</option>
                </select>
              </div>

              {/* Common Fields */}
              <div className="mb-4">
                <label className="block text-gray-300 mb-2">Title</label>
                <input
                  type="text"
                  value={newPost.title}
                  onChange={(e) => setNewPost(prev => ({ ...prev, title: e.target.value }))}
                  className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                  required
                />
              </div>

              {/* Track-specific fields */}
              {newPost.type === 'track' && (
                <>
                  <div className="mb-4">
                    <label className="block text-gray-300 mb-2">Caption</label>
                    <textarea
                      value={newPost.caption}
                      onChange={(e) => setNewPost(prev => ({ ...prev, caption: e.target.value }))}
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500 h-24"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-gray-300 mb-2">Genre</label>
                      <input
                        type="text"
                        value={newPost.genre}
                        onChange={(e) => setNewPost(prev => ({ ...prev, genre: e.target.value }))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-300 mb-2">Price (SOL)</label>
                      <input
                        type="number"
                        step="0.1"
                        value={newPost.price}
                        onChange={(e) => setNewPost(prev => ({ ...prev, price: e.target.value }))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>
                  </div>
                  <div className="mb-4">
                    <label className="block text-gray-300 mb-2">Audio File</label>
                    <input
                      type="file"
                      accept="audio/*"
                      onChange={(e) => handleFileChange('audioFile', e.target.files[0])}
                      className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-violet-600 file:text-white hover:file:bg-violet-700"
                    />
                  </div>
                </>
              )}

              {/* Event-specific fields */}
              {newPost.type === 'event' && (
                <>
                  <div className="mb-4">
                    <label className="block text-gray-300 mb-2">Description</label>
                    <textarea
                      value={newPost.description}
                      onChange={(e) => setNewPost(prev => ({ ...prev, description: e.target.value }))}
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500 h-24"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="block text-gray-300 mb-2">Date</label>
                      <input
                        type="date"
                        value={newPost.date}
                        onChange={(e) => setNewPost(prev => ({ ...prev, date: e.target.value }))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-300 mb-2">Location</label>
                      <input
                        type="text"
                        value={newPost.location}
                        onChange={(e) => setNewPost(prev => ({ ...prev, location: e.target.value }))}
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* Cover Image */}
              <div className="mb-4">
                <label className="block text-gray-300 mb-2">Cover Image</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => handleFileChange('coverImage', e.target.files[0])}
                  className="text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-violet-600 file:text-white hover:file:bg-violet-700"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex space-x-3">
                <button
                  type="submit"
                  className="bg-violet-600 hover:bg-violet-700 text-white px-4 py-2 rounded-lg transition-colors"
                >
                  Post
                </button>
                <button
                  type="button"
                  onClick={handleCreatePost}
                  className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
      
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="w-12 h-12 border-4 border-dashed rounded-full animate-spin border-violet-600"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {posts.map(post => (
            <div key={post.id} className="bg-gray-800 rounded-lg overflow-hidden">
              {/* Post Header */}
              <div className="p-4 border-b border-gray-700">
                <div className="flex items-center">
                  <div className="w-10 h-10 rounded-full overflow-hidden mr-3 bg-gray-700">
                    <img 
                      src={post.user.profilePicture}
                      alt={post.user.username}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        // Fallback to a different avatar style if the first one fails
                        e.target.src = generateAvatarUrl(post.user.username, 'initials');
                      }}
                    />
                  </div>
                  <div>
                    <div className="font-medium flex items-center">
                      {post.user.username}
                      {post.user.isArtist && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-violet-600/20 text-violet-400 rounded-full">Artist</span>
                      )}
                      {post.user.isLabel && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-blue-600/20 text-blue-400 rounded-full">Label</span>
                      )}
                      {post.user.isAdmin && (
                        <span className="ml-2 px-2 py-0.5 text-xs bg-red-600/20 text-red-400 rounded-full">Admin</span>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      {new Date(post.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Post Content */}
              <div className="p-4">
                {post.type === 'track' && (
                  <div>
                    <h3 className="text-xl font-medium mb-2">{post.content.title}</h3>
                    <p className="text-gray-300 mb-4">{post.content.caption}</p>
                    <div className="bg-gray-900 rounded-lg overflow-hidden mb-4">
                      <div className="flex items-center p-3">
                        <div className="w-16 h-16 bg-violet-600/20 rounded-md flex-shrink-0 flex items-center justify-center mr-3 overflow-hidden">
                          <img 
                            src={post.content.coverImage}
                            alt={post.content.title}
                            className="w-full h-full object-cover rounded-md"
                            onError={(e) => {
                              // Fallback to icon if image fails
                              e.target.style.display = 'none';
                              e.target.nextElementSibling.style.display = 'block';
                            }}
                          />
                          <Music size={32} className="text-violet-400" style={{ display: 'none' }} />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-gray-400 mb-1">{post.content.genre}</p>
                          <div className="bg-gray-800 rounded-lg p-2">
                            <div className="text-xs text-gray-500 mb-1">Audio Preview</div>
                            <div className="h-8 bg-gradient-to-r from-violet-600/30 to-purple-600/30 rounded flex items-center justify-center">
                              <span className="text-xs text-gray-400">🎵 Preview not available</span>
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex justify-between items-center p-3 border-t border-gray-700">
                        <span className="text-gray-300">Price: {post.content.price} SOL</span>
                        <button 
                          onClick={() => handleBuy(post.id)} 
                          className="bg-violet-600 hover:bg-violet-700 text-white px-3 py-1 rounded text-sm"
                        >
                          Buy Now
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                
                {post.type === 'event' && (
                  <div>
                    <h3 className="text-xl font-medium mb-2">{post.content.title}</h3>
                    <p className="text-gray-300 mb-4">{post.content.description}</p>
                    <div className="bg-gray-900 rounded-lg overflow-hidden mb-4">
                      <img 
                        src={post.content.coverImage}
                        alt={post.content.title}
                        className="w-full h-48 object-cover"
                      />
                      <div className="p-4">
                        <div className="flex items-center mb-2">
                          <Calendar size={16} className="text-violet-400 mr-2" />
                          <span>{post.content.date}</span>
                        </div>
                        <div className="flex items-center">
                          <MapPin size={16} className="text-violet-400 mr-2" />
                          <span>{post.content.location}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                
                {post.type === 'challenge' && (
                  <div>
                    <h3 className="text-xl font-medium mb-2">{post.content.title}</h3>
                    <p className="text-gray-300 mb-4">{post.content.description}</p>
                    <div className="bg-gray-900 rounded-lg p-4 mb-4">
                      <div className="flex items-center mb-3">
                        <Clock size={16} className="text-violet-400 mr-2" />
                        <span>Deadline: {post.content.deadline}</span>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium text-violet-400 mb-2">Prizes:</h4>
                        <ul className="list-disc pl-5 text-sm space-y-1">
                          {post.content.prizes.map((prize, index) => (
                            <li key={index}>{prize}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Interactions */}
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center space-x-4">
                    <button 
                      onClick={() => handleLike(post.id)}
                      className="flex items-center text-gray-400 hover:text-violet-400 transition-colors"
                    >
                      <Heart size={18} className="mr-1" />
                      <span>{post.likes}</span>
                    </button>
                    <div className="flex items-center text-gray-400">
                      <MessageCircle size={18} className="mr-1" />
                      <span>{post.comments.length}</span>
                    </div>
                  </div>
                  <div>
                    <button className="text-gray-400 hover:text-violet-400 transition-colors">
                      <Share size={18} />
                    </button>
                  </div>
                </div>
              </div>
              
              {/* Comments */}
              {post.comments.length > 0 && (
                <div className="px-4 py-3 border-t border-gray-700">
                  <h4 className="text-sm font-medium mb-2">Comments</h4>
                  <div className="space-y-3">
                    {post.comments.map(comment => (
                      <div key={comment.id} className="flex items-start">
                        <div className="w-8 h-8 rounded-full flex-shrink-0 mr-2 overflow-hidden bg-gray-700">
                          <img 
                            src={comment.user.profilePicture}
                            alt={comment.user.username}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              e.target.src = generateAvatarUrl(comment.user.username, 'initials');
                            }}
                          />
                        </div>
                        <div className="flex-1">
                          <div className="bg-gray-700 rounded-lg p-2">
                            <span className="font-medium text-sm">{comment.user.username}</span>
                            <p className="text-sm">{comment.text}</p>
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {new Date(comment.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Add Comment */}
              <div className="p-4 border-t border-gray-700">
                <div className="flex items-center">
                  <div className="w-8 h-8 rounded-full mr-2 overflow-hidden bg-gray-700">
                    <img 
                      src={user.profilePicture || generateAvatarUrl(user.username, 'avataaars')}
                      alt={user.username}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.target.src = generateAvatarUrl(user.username, 'initials');
                      }}
                    />
                  </div>
                  <input 
                    type="text" 
                    placeholder="Add a comment..." 
                    className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-violet-500"
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