const DEFAULT_BASE_URL = typeof window !== 'undefined' ? window.location.origin : '';
const API_BASE_URL = (process.env.REACT_APP_API_URL || DEFAULT_BASE_URL).replace(/\/$/, '');

/**
 * Base API service for making requests to the backend
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
  
  // Get token from localStorage if it exists
  const token = localStorage.getItem('token');
  
  // Set default headers
  const headers = {
    'Content-Type': 'application/json',
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
  
  // Make request
  const response = await fetch(url, requestOptions);
  
  // Parse JSON response
  const data = await response.json();
  
  // Check if request was successful
  if (!response.ok) {
    throw new Error(data.message || 'Something went wrong');
  }
  
  return data;
}
