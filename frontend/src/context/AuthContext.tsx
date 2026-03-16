import React, { createContext, useContext, useState, useEffect, type ReactNode, useMemo } from 'react';
import axios, { type AxiosInstance } from 'axios';
import type { User, AuthState } from '../types';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  axiosInstance: AxiosInstance;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

// Create a single axios instance
export const axiosInstance = axios.create({
  baseURL: '/api', // Proxy is set in vite.config.ts usually, or we can use full URL
  headers: {
    'Content-Type': 'application/json',
  },
});

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: true,
  });

  const login = (token: string, user: User) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    setState({
      token,
      user,
      isAuthenticated: true,
      isLoading: false,
    });
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setState({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  };

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    if (storedToken && storedUser) {
        try {
            setState({
                token: storedToken,
                user: JSON.parse(storedUser),
                isAuthenticated: true,
                isLoading: false
            });
        } catch (e) {
            console.error("Failed to parse stored user", e);
            localStorage.removeItem('user');
            setState(s => ({ ...s, isLoading: false }));
        }
    } else {
        setState(s => ({ ...s, isLoading: false }));
    }
  }, []);

  // Setup interceptors
  useEffect(() => {
    const reqInterceptor = axiosInstance.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    const resInterceptor = axiosInstance.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          logout();
        }
        return Promise.reject(error);
      }
    );

    return () => {
      axiosInstance.interceptors.request.eject(reqInterceptor);
      axiosInstance.interceptors.response.eject(resInterceptor);
    };
  }, []); // Dependencies empty to avoid re-binding interceptors needlessly

  const value = useMemo(() => ({
    ...state,
    login,
    logout,
    axiosInstance
  }), [state]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
