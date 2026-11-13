import { API_BASE_URL, apiClient } from './client';
import type { ChatMessage, ChatSession } from '../types';

export interface SendMessageResponse {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

export function getChatWebSocketUrl(sessionId: number, token: string): string {
  let wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let host = window.location.host;

  if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
    try {
      const parsed = new URL(API_BASE_URL);
      wsProto = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
      host = parsed.host;
    } catch {
      // Keep default host
    }
  }

  return `${wsProto}//${host}/ws/chat/${sessionId}/?token=${encodeURIComponent(token)}`;
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

  closeSession: async (sessionId: number): Promise<ChatSession> => {
    const { data } = await apiClient.post<ChatSession>(
      `/chat/sessions/${sessionId}/close/`
    );
    return data;
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

