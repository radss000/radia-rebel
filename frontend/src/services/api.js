// Détection intelligente de l'environnement
const getApiBaseUrl = () => {
  // En production, utiliser la variable d'environnement
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // En développement local
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:5001';
  }
  
  // Fallback pour production si pas de variable d'env
  return 'https://rebel-backend.railway.app'; // À remplacer par votre URL backend
};

const API_BASE_URL = getApiBaseUrl();

/**
 * Base API service for making requests to the backend
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  
  // Get token from localStorage if it exists
  const token = localStorage.getItem('token');
  
  // Set default headers
  const headers = {
    ...options.headers
  };
  
  // Add authorization header if token exists
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  // Create request options
  const requestOptions = {
    ...options,
    headers
  };
  
  try {
    console.log(`🌐 API Request: ${options.method || 'GET'} ${url}`);
    
    // Make request
    const response = await fetch(url, requestOptions);
    
    // Parse JSON response
    const data = await response.json();
    
    // Check if request was successful
    if (!response.ok) {
      console.error(`❌ API Error: ${response.status}`, data);
      throw new Error(data.message || `HTTP ${response.status}: Something went wrong`);
    }
    
    console.log(`✅ API Success: ${options.method || 'GET'} ${url}`);
    return data;
  } catch (error) {
    console.error('💥 API Request failed:', error);
    
    // Si c'est une erreur de réseau, donner plus d'infos
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      throw new Error(`Impossible de contacter le serveur. Vérifiez que l'API backend est démarrée à ${API_BASE_URL}`);
    }
    
    throw error;
  }
}