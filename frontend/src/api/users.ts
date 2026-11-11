import { apiClient } from './client';
import type { ActivityLog, Address, PaginatedResponse, Role, RoleName, User } from '../types';

export const usersApi = {
  getRoles: async (): Promise<Role[]> => {
    const { data } = await apiClient.get<Role[]>('/roles/');
    return data;
  },

  getUsers: async (params?: {
    page?: number;
    search?: string;
    role__name?: string;
  }): Promise<PaginatedResponse<User>> => {
    const { data } = await apiClient.get<PaginatedResponse<User>>('/users/', { params });
    return data;
  },

  createUser: async (payload: {
    username: string;
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
    phone?: string;
    role: RoleName;
    initial_balance?: string;
    account_type?: string;
    create_bank_account?: boolean;
  }): Promise<User> => {
    const { data } = await apiClient.post<User>('/users/', payload);
    return data;
  },

  openBankAccount: async (
    userId: number,
    payload: { account_type: 'savings' | 'current' | 'salary'; initial_balance?: string }
  ): Promise<User> => {
    const { data } = await apiClient.post<User>(`/users/${userId}/open-account/`, payload);
    return data;
  },

  getActivities: async (params?: {
    page?: number;
    category?: string;
    action?: string;
    subject_user?: number;
    actor?: number;
    search?: string;
    mine?: 'true';
  }): Promise<PaginatedResponse<ActivityLog>> => {
    const { data } = await apiClient.get<PaginatedResponse<ActivityLog>>('/activities/', {
      params,
    });
    return data;
  },

  updateUser: async (
    id: number,
    payload: Partial<{
      email: string;
      first_name: string;
      last_name: string;
      phone: string;
      role: RoleName;
      is_active: boolean;
    }>
  ): Promise<User> => {
    const { data } = await apiClient.patch<User>(`/users/${id}/`, payload);
    return data;
  },

  deleteUser: async (id: number): Promise<void> => {
    await apiClient.delete(`/users/${id}/`);
  },

  getAddresses: async (): Promise<Address[]> => {
    const { data } = await apiClient.get<Address[]>('/addresses/');
    return data;
  },

  createAddress: async (
    payload: Omit<Address, 'id' | 'user' | 'created_at' | 'updated_at'>
  ): Promise<Address> => {
    const { data } = await apiClient.post<Address>('/addresses/', payload);
    return data;
  },

  updateAddress: async (
    id: number,
    payload: Partial<Omit<Address, 'id' | 'user' | 'created_at' | 'updated_at'>>
  ): Promise<Address> => {
    const { data } = await apiClient.patch<Address>(`/addresses/${id}/`, payload);
    return data;
  },

  deleteAddress: async (id: number): Promise<void> => {
    await apiClient.delete(`/addresses/${id}/`);
  },
};

