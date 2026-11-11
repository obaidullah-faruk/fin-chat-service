import { apiClient } from './client';
import type { ChequeBookRequest, ChequeStatus, PaginatedResponse } from '../types';

export const chequeApi = {
  getRequests: async (params?: {
    page?: number;
    status?: string;
    mine?: 'true';
    user_id?: number;
  }): Promise<PaginatedResponse<ChequeBookRequest>> => {
    const { data } = await apiClient.get<PaginatedResponse<ChequeBookRequest>>(
      '/cheque/requests/',
      { params }
    );
    return data;
  },

  createRequest: async (payload: {
    leaves_requested: number;
    delivery_address?: number | null;
    remarks?: string;
  }): Promise<ChequeBookRequest> => {
    const { data } = await apiClient.post<ChequeBookRequest>('/cheque/request/', payload);
    return data;
  },

  reviewRequest: async (
    id: number,
    payload: { status: Extract<ChequeStatus, 'approved' | 'rejected' | 'issued'>; remarks?: string }
  ): Promise<ChequeBookRequest> => {
    const { data } = await apiClient.patch<ChequeBookRequest>(
      `/cheque/requests/${id}/review/`,
      payload
    );
    return data;
  },
};

