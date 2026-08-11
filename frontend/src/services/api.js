import axios from 'axios';

// Get API base URL from environment variables, fallback to localhost:8000
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach Admin Token if present
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('startuptn_admin_token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export const apiService = {
  // Public Chat Endpoint
  chat: async (question) => {
    try {
      const response = await apiClient.post('/api/chat', { question });
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Server error';
    }
  },

  // Admin Authentication
  login: async (password) => {
    try {
      const response = await apiClient.post('/api/admin/login', { password });
      const { token } = response.data;
      if (token) {
        localStorage.setItem('startuptn_admin_token', token);
      }
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Invalid Credentials';
    }
  },

  // Logout admin
  logout: () => {
    localStorage.removeItem('startuptn_admin_token');
  },

  // Check if admin is currently authenticated
  isAdminAuthenticated: () => {
    return !!localStorage.getItem('startuptn_admin_token');
  },

  // Get knowledge base statistics and indexed files list
  getStatus: async () => {
    try {
      const response = await apiClient.get('/api/admin/status');
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Failed to fetch status';
    }
  },

  // Upload PDF document to backend data folder
  uploadDocument: async (file) => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await apiClient.post('/api/admin/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Upload failed';
    }
  },

  // Sync database with the local files
  syncDatabase: async () => {
    try {
      const response = await apiClient.post('/api/admin/sync');
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Sync failed';
    }
  },

  // Delete document by filename
  deleteDocument: async (filename) => {
    try {
      const response = await apiClient.delete(`/api/admin/documents/${encodeURIComponent(filename)}`);
      return response.data;
    } catch (error) {
      throw error.response?.data || error.message || 'Deletion failed';
    }
  },
};
