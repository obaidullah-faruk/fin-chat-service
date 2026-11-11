import { apiClient } from './client';
import type {
  Endorsement,
  EndorsementStatus,
  EndorsementType,
  PaginatedResponse,
} from '../types';

export const endorsementApi = {
  getEndorsements: async (params?: {
    page?: number;
    status?: string;
    mine?: 'true';
    user_id?: number;
  }): Promise<PaginatedResponse<Endorsement>> => {
    const { data } = await apiClient.get<PaginatedResponse<Endorsement>>(
      '/endorsements/',
      { params }
    );
    return data;
  },

  createEndorsement: async (payload: {
    endorsement_type: EndorsementType;
    amount?: string;
    passport_number?: string;
    notes?: string;
  }): Promise<Endorsement> => {
    const { data } = await apiClient.post<Endorsement>('/endorsements/', payload);
    return data;
  },

  reviewEndorsement: async (
    id: number,
    payload: {
      status: Extract<EndorsementStatus, 'approved' | 'rejected'>;
      review_remarks?: string;
    }
  ): Promise<Endorsement> => {
    const { data } = await apiClient.patch<Endorsement>(
      `/endorsements/${id}/review/`,
      payload
    );
    return data;
  },
};

