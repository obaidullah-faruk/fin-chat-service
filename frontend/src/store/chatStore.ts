import { create } from 'zustand';

export type ChatWidgetMode = 'collapsed' | 'expanded' | 'maximized';

interface ChatState {
  mode: ChatWidgetMode;
  activeSessionId: number | null;
  setMode: (mode: ChatWidgetMode) => void;
  openExpanded: () => void;
  openMaximized: () => void;
  collapse: () => void;
  setActiveSessionId: (id: number | null) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  mode: 'collapsed',
  activeSessionId: null,
  setMode: (mode) => set({ mode }),
  openExpanded: () => set({ mode: 'expanded' }),
  openMaximized: () => set({ mode: 'maximized' }),
  collapse: () => set({ mode: 'collapsed' }),
  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
  reset: () => set({ mode: 'collapsed', activeSessionId: null }),
}));

