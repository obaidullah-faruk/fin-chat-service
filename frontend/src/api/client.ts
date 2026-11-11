import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';

export const API_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

function getHeaderAuthorization(headers: InternalAxiosRequestConfig['headers']): string | null {
  if (!headers) return null;
  if (typeof headers.get === 'function') {
    const val = headers.get('Authorization');
    return typeof val === 'string' ? val : null;
  }
  const raw = (headers as Record<string, unknown>).Authorization;
  return typeof raw === 'string' ? raw : null;
}

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (config.headers) {
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    } else {
      delete config.headers.Authorization;
    }
  }
  return config;
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    const statusCode = error.response?.status;

    if (
      statusCode === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.url?.includes('/auth/login/') &&
      !originalRequest.url?.includes('/auth/logout/') &&
      !originalRequest.url?.includes('/auth/token/refresh/')
    ) {
      const state = useAuthStore.getState();
      const sentAuth = getHeaderAuthorization(originalRequest.headers);
      const currentAuth = state.accessToken ? `Bearer ${state.accessToken}` : null;

      // Ignore 401 from an older session's in-flight request after logout or account switch
      if (!state.accessToken || (sentAuth && currentAuth && sentAuth !== currentAuth)) {
        return Promise.reject(error);
      }

      const refreshStartedForToken = state.refreshToken;
      if (!refreshStartedForToken) {
        state.logout();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              const latestState = useAuthStore.getState();
              if (!latestState.accessToken || latestState.refreshToken !== refreshStartedForToken) {
                reject(new Error('Session changed while waiting for token refresh.'));
                return;
              }
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
              }
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const res = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
          refresh: refreshStartedForToken,
        });
        const latestState = useAuthStore.getState();
        if (!latestState.accessToken || latestState.refreshToken !== refreshStartedForToken) {
          const sessionErr = new Error('Session changed during token refresh.');
          processQueue(sessionErr, null);
          return Promise.reject(sessionErr);
        }

        const newAccess: string = res.data.access;
        const newRefresh: string | undefined = res.data.refresh;
        latestState.setTokens(newAccess, newRefresh);
        processQueue(null, newAccess);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        }
        return apiClient(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        const latestState = useAuthStore.getState();
        if (latestState.refreshToken === refreshStartedForToken) {
          latestState.logout();
        }
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export function getApiErrorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as Record<string, unknown> | undefined;
    if (!data) return err.message || fallback;

    if (typeof data.detail === 'string' && data.detail !== 'Request validation failed.') {
      return data.detail;
    }
    if (Array.isArray(data.non_field_errors) && data.non_field_errors.length > 0) {
      return String(data.non_field_errors[0]);
    }
    for (const [key, val] of Object.entries(data)) {
      if (key === 'status_code' || key === 'detail') continue;
      if (Array.isArray(val) && val.length > 0) {
        return `${key}: ${String(val[0])}`;
      }
      if (typeof val === 'string') {
        return `${key}: ${val}`;
      }
    }
    if (typeof data.detail === 'string') {
      return data.detail;
    }
  }
  return fallback;
}
