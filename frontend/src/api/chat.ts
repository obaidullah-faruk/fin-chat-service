import { apiClient } from './client';
import type { ChatMessage, ChatSession } from '../types';

export interface SendMessageResponse {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

export const chatApi = {
  getSessions: async (): Promise<ChatSession[]> => {
    const { data } = await apiClient.get<ChatSession[]>('/chat/sessions/');
    return data;
  },

  createSession: async (title = ''): Promise<ChatSession> => {
    const { data } = await apiClient.post<ChatSession>('/chat/sessions/', { title });
    return data;
  },

  deleteSession: async (sessionId: number): Promise<void> => {
    await apiClient.delete(`/chat/sessions/${sessionId}/`);
  },

  getMessages: async (sessionId: number): Promise<ChatMessage[]> => {
    const { data } = await apiClient.get<ChatMessage[]>(
      `/chat/sessions/${sessionId}/messages/`
    );
    return data;
  },

  sendMessage: async (
    sessionId: number,
    content: string
  ): Promise<SendMessageResponse> => {
    const { data } = await apiClient.post<SendMessageResponse>(
      `/chat/sessions/${sessionId}/agent/`,
      { content }
    );
    return data;
  },
};

