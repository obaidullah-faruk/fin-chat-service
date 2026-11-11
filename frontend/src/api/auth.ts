import { apiClient } from './client';
import type { User } from '../types';

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const { data } = await apiClient.post<LoginResponse>('/auth/login/', {
      username,
      password,
    });
    return data;
  },

  logout: async (refresh: string): Promise<void> => {
    await apiClient.post('/auth/logout/', { refresh });
  },

  getMe: async (): Promise<User> => {
    const { data } = await apiClient.get<User>('/auth/me/');
    return data;
  },

  updateMe: async (payload: {
    first_name?: string;
    last_name?: string;
    phone?: string;
    date_of_birth?: string | null;
    national_id?: string;
    bio?: string;
  }): Promise<User> => {
    const { data } = await apiClient.patch<User>('/auth/me/', payload);
    return data;
  },
};

