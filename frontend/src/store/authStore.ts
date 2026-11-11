import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { queryClient } from '../api/queryClient';
import type { RoleName, User, WorkspaceMode } from '../types';
import { useChatStore } from './chatStore';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  workspace: WorkspaceMode;
  setAuth: (access: string, refresh: string, user: User) => void;
  setTokens: (access: string, refresh?: string) => void;
  setUser: (user: User) => void;
  setWorkspace: (mode: WorkspaceMode) => void;
  logout: () => void;
  hasRole: (...roles: RoleName[]) => boolean;
}

function defaultWorkspaceForUser(user: User | null): WorkspaceMode {
  if (!user || user.role === 'customer') return 'personal';
  return 'staff';
}

function clearCachesAndChatState() {
  void queryClient.cancelQueries();
  queryClient.clear();
  useChatStore.getState().reset();
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      workspace: 'personal',
      setAuth: (accessToken, refreshToken, user) => {
        clearCachesAndChatState();
        set({
          accessToken,
          refreshToken,
          user,
          workspace: defaultWorkspaceForUser(user),
        });
      },
      setTokens: (accessToken, refreshToken) =>
        set((state) => {
          if (!state.accessToken) {
            return state;
          }
          return {
            accessToken,
            refreshToken: refreshToken ?? state.refreshToken,
          };
        }),
      setUser: (user) =>
        set((state) => {
          if (!state.accessToken || (state.user && state.user.id !== user.id)) {
            return state;
          }
          let nextWorkspace = state.workspace;
          if (user.role === 'customer') {
            nextWorkspace = 'personal';
          } else if (state.workspace === 'personal' && !user.bank_account) {
            nextWorkspace = 'staff';
          }
          return { user, workspace: nextWorkspace };
        }),
      setWorkspace: (mode) => {
        const user = get().user;
        if (!user) return;
        if (user.role === 'customer') {
          set({ workspace: 'personal' });
          return;
        }
        if (mode === 'personal' && !user.bank_account) {
          return;
        }
        set({ workspace: mode });
      },
      logout: () => {
        clearCachesAndChatState();
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          workspace: 'personal',
        });
      },
      hasRole: (...roles) => {
        const userRole = get().user?.role;
        return Boolean(userRole && roles.includes(userRole));
      },
    }),
    {
      name: 'finchat-auth',
    }
  )
);

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === 'finchat-auth') {
      clearCachesAndChatState();
      void useAuthStore.persist.rehydrate();
    }
  });
}
