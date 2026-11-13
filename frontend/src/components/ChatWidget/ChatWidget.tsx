import { useEffect, useRef, useState } from 'react';
import {
  Add as AddIcon,
  Chat as ChatIcon,
  CloseFullscreen as RestoreIcon,
  DeleteOutlined as DeleteIcon,
  OpenInFull as MaximizeIcon,
  Remove as MinimizeIcon,
  SmartToy as BotIcon,
  Wifi as WifiIcon,
  WifiOff as WifiOffIcon,
} from '@mui/icons-material';
import {
  Box,
  Dialog,
  Divider,
  Fab,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  CircularProgress,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { chatApi, getChatWebSocketUrl } from '../../api/chat';
import { useAuthStore } from '../../store/authStore';
import { useChatStore } from '../../store/chatStore';
import type { ChatSession, StreamEvent } from '../../types';
import { ChatInputBar } from './ChatInputBar';
import { ChatMessageList } from './ChatMessageList';
import type { StatusState } from './ChatStatusPill';
import { getToolProgressMessage } from './chatUtils';

// ---------------------------------------------------------------------------
// Chat Widget – top-level orchestrator
// ---------------------------------------------------------------------------

export function ChatWidget() {
  const { user, accessToken } = useAuthStore();
  const {
    mode,
    activeSessionId,
    openExpanded,
    openMaximized,
    collapse,
    setActiveSessionId,
  } = useChatStore();

  const queryClient = useQueryClient();
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<StatusState | null>(null);
  const [streamingTokens, setStreamingTokens] = useState('');
  const [optimisticUserMsg, setOptimisticUserMsg] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const isOpen = mode !== 'collapsed';

  // ── Sessions ──────────────────────────────────────────────────────────────

  const { data: sessions = [], isLoading: sessionsLoading } = useQuery({
    queryKey: ['chat-sessions', user?.id],
    queryFn: chatApi.getSessions,
    enabled: Boolean(accessToken && user && isOpen),
  });

  useEffect(() => {
    if (isOpen && sessions.length > 0 && activeSessionId === null) {
      setActiveSessionId(sessions[0].id);
    }
  }, [isOpen, sessions, activeSessionId, setActiveSessionId]);

  // ── Messages ──────────────────────────────────────────────────────────────

  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', activeSessionId, user?.id],
    queryFn: () => chatApi.getMessages(activeSessionId!),
    enabled: Boolean(accessToken && user && isOpen && activeSessionId !== null),
  });

  // ── WebSocket ─────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!isOpen || !activeSessionId || !accessToken) {
      wsRef.current?.close();
      wsRef.current = null;
      setWsConnected(false);
      return;
    }

    let ws: WebSocket;
    try {
      ws = new WebSocket(getChatWebSocketUrl(activeSessionId, accessToken));
      wsRef.current = ws;
    } catch (err) {
      console.warn('Failed to open WebSocket:', err);
      setWsConnected(false);
      return;
    }

    ws.onopen = () => setWsConnected(true);

    ws.onmessage = (event) => {
      try {
        const data: StreamEvent = JSON.parse(event.data as string);
        handleStreamEvent(data);
      } catch {
        // Ignore non-JSON frames
      }
    };

    ws.onerror = () => setWsConnected(false);
    ws.onclose = () => {
      setWsConnected(false);
      if (wsRef.current === ws) wsRef.current = null;
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
      setWsConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, activeSessionId, accessToken]);

  /**
   * Handle a single streaming event from the WebSocket.
   * Tool names are translated to user-friendly messages here so the UI
   * never surfaces raw internal identifiers like `get_balance`.
   */
  function handleStreamEvent(data: StreamEvent) {
    switch (data.type) {
      case 'status':
        setStatus({ stage: data.stage, message: data.message });
        break;

      case 'tool_call_start':
        // Show a friendly in-progress message, not the raw tool name
        setStatus({
          stage: 'tool',
          message: getToolProgressMessage(data.tool_name),
        });
        break;

      case 'tool_call_end':
        // Keep current status visible until next meaningful event
        break;

      case 'token':
        setStatus(null);
        setStreamingTokens((prev) => prev + data.token);
        break;

      case 'done':
        setStatus(null);
        setStreamingTokens('');
        setOptimisticUserMsg(null);
        queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
        queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSessionId] });
        break;

      case 'error':
        setStatus({
          stage: 'error',
          message: data.error || 'AI processing encountered an issue.',
        });
        setTimeout(() => {
          setStatus(null);
          setStreamingTokens('');
          setOptimisticUserMsg(null);
          queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSessionId] });
        }, 3500);
        break;
    }
  }

  // ── Auto-scroll ───────────────────────────────────────────────────────────

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, mode, streamingTokens, status, optimisticUserMsg]);

  // ── Mutations ─────────────────────────────────────────────────────────────

  const createSessionMutation = useMutation({
    mutationFn: () => chatApi.createSession(''),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      setActiveSessionId(session.id);
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (id: number) => chatApi.deleteSession(id),
    onSuccess: (_data, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      if (activeSessionId === deletedId) setActiveSessionId(null);
    },
  });

  /**
   * HTTP fallback mutation (used when WebSocket is not connected).
   */
  const sendMessageMutation = useMutation({
    mutationFn: async (text: string) => {
      let targetSessionId = activeSessionId;
      if (!targetSessionId) {
        const newSession = await chatApi.createSession('');
        targetSessionId = newSession.id;
        setActiveSessionId(targetSessionId);
      }
      await chatApi.sendMessage(targetSessionId, text);
      return targetSessionId;
    },
    onSuccess: (targetSessionId) => {
      setOptimisticUserMsg(null);
      setStatus(null);
      setStreamingTokens('');
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['chat-messages', targetSessionId] });
    },
    onError: () => {
      setOptimisticUserMsg(null);
      setStatus(null);
      setStreamingTokens('');
    },
  });

  // ── Guard ─────────────────────────────────────────────────────────────────

  if (!accessToken || !user) return null;

  const isSending = sendMessageMutation.isPending || Boolean(optimisticUserMsg);

  // ── Send handler ──────────────────────────────────────────────────────────

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isSending) return;
    setInput('');

    // Ensure we have an active session before sending
    let targetSessionId = activeSessionId;
    if (!targetSessionId) {
      try {
        const newSession = await chatApi.createSession('');
        targetSessionId = newSession.id;
        setActiveSessionId(targetSessionId);
      } catch (err) {
        console.error('Failed to create session:', err);
        return;
      }
    }

    setOptimisticUserMsg(trimmed);
    setStreamingTokens('');

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setStatus({ stage: 'init', message: 'Connecting to FinChat banking sub-agents...' });
      wsRef.current.send(JSON.stringify({ content: trimmed }));
    } else {
      setStatus({ stage: 'init', message: 'Contacting FinChat AI Service...' });
      sendMessageMutation.mutate(trimmed);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  if (mode === 'collapsed') {
    return (
      <Tooltip title="Open FinChat Assistant" placement="left">
        <Fab
          color="primary"
          aria-label="Open chat"
          onClick={openExpanded}
          sx={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 1200,
            boxShadow: '0 4px 14px rgba(79, 70, 229, 0.4)',
          }}
        >
          <ChatIcon />
        </Fab>
      </Tooltip>
    );
  }

  if (mode === 'maximized') {
    return (
      <Dialog
        fullScreen
        open
        onClose={collapse}
        slotProps={{
          paper: {
            sx: {
              display: 'flex',
              flexDirection: 'column',
              bgcolor: 'background.default',
              '& .MuiPaper-root': { borderRadius: 0 },
            },
          },
        }}
      >
        <ChatHeader
          wsConnected={wsConnected}
          isMaximized
          onRestore={openExpanded}
          onCollapse={collapse}
        />

        <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
          <ChatSessionSidebar
            sessions={sessions}
            isLoading={sessionsLoading}
            activeSessionId={activeSessionId}
            onSelectSession={setActiveSessionId}
            onDeleteSession={(id) => deleteSessionMutation.mutate(id)}
            onNewSession={() => createSessionMutation.mutate()}
            isCreating={createSessionMutation.isPending}
          />
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <ChatMessageList
              messages={messages}
              isLoading={messagesLoading}
              optimisticUserMsg={optimisticUserMsg}
              streamingTokens={streamingTokens}
              status={status}
              bottomRef={messagesEndRef}
            />
            <ChatInputBar
              value={input}
              onChange={setInput}
              onSend={handleSend}
              disabled={isSending}
            />
          </Box>
        </Box>
      </Dialog>
    );
  }

  // Expanded floating panel
  return (
    <Paper
      elevation={8}
      sx={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        width: 420,
        height: 600,
        maxWidth: 'calc(100vw - 32px)',
        maxHeight: 'calc(100vh - 48px)',
        zIndex: 1300,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        borderRadius: 2.5,
      }}
    >
      <ChatHeader
        wsConnected={wsConnected}
        isMaximized={false}
        onNewChat={() => createSessionMutation.mutate()}
        isCreatingChat={createSessionMutation.isPending}
        onMaximize={openMaximized}
        onCollapse={collapse}
      />

      {sessions.length > 0 && (
        <Box sx={{ px: 1.5, py: 0.75, borderBottom: '1px solid #e2e8f0', bgcolor: 'background.paper' }}>
          <Select
            fullWidth
            size="small"
            value={activeSessionId ?? ''}
            onChange={(e) => setActiveSessionId(Number(e.target.value))}
            displayEmpty
            variant="standard"
            disableUnderline
            sx={{ fontSize: '0.82rem' }}
          >
            {sessions.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.title || `Chat Session #${s.id}`}
              </MenuItem>
            ))}
          </Select>
        </Box>
      )}

      <ChatMessageList
        messages={messages}
        isLoading={messagesLoading}
        optimisticUserMsg={optimisticUserMsg}
        streamingTokens={streamingTokens}
        status={status}
        bottomRef={messagesEndRef}
      />
      <ChatInputBar
        value={input}
        onChange={setInput}
        onSend={handleSend}
        disabled={isSending}
      />
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Local sub-components (layout-level, not shared)
// ---------------------------------------------------------------------------

interface ChatHeaderProps {
  wsConnected: boolean;
  isMaximized: boolean;
  onRestore?: () => void;
  onCollapse: () => void;
  onNewChat?: () => void;
  isCreatingChat?: boolean;
  onMaximize?: () => void;
}

function ChatHeader({
  wsConnected,
  isMaximized,
  onRestore,
  onCollapse,
  onNewChat,
  isCreatingChat,
  onMaximize,
}: ChatHeaderProps) {
  const wsTooltip = wsConnected ? 'Live streaming connected' : 'Connecting to live stream...';

  return (
    <Box
      sx={{
        px: 2,
        py: 1.25,
        bgcolor: 'primary.main',
        color: 'primary.contrastText',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <BotIcon fontSize={isMaximized ? 'medium' : 'small'} />
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          FinChat Assistant
        </Typography>
        <Tooltip title={wsTooltip}>
          {wsConnected ? (
            <WifiIcon sx={{ fontSize: 16, color: '#86efac' }} />
          ) : (
            <WifiOffIcon sx={{ fontSize: 16, color: 'rgba(255,255,255,0.6)' }} />
          )}
        </Tooltip>
      </Stack>

      <Stack direction="row" spacing={0.5}>
        {isMaximized ? (
          <>
            <Tooltip title="Restore floating panel">
              <IconButton size="small" color="inherit" onClick={onRestore}>
                <RestoreIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Minimize">
              <IconButton size="small" color="inherit" onClick={onCollapse}>
                <MinimizeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </>
        ) : (
          <>
            <Tooltip title="New chat">
              <span>
                <IconButton
                  size="small"
                  color="inherit"
                  onClick={onNewChat}
                  disabled={isCreatingChat}
                >
                  {isCreatingChat ? (
                    <CircularProgress size={16} color="inherit" />
                  ) : (
                    <AddIcon fontSize="small" />
                  )}
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Expand full view">
              <IconButton size="small" color="inherit" onClick={onMaximize}>
                <MaximizeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Minimize">
              <IconButton size="small" color="inherit" onClick={onCollapse}>
                <MinimizeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </>
        )}
      </Stack>
    </Box>
  );
}

interface ChatSessionSidebarProps {
  sessions: ChatSession[];
  isLoading: boolean;
  activeSessionId: number | null;
  onSelectSession: (id: number) => void;
  onDeleteSession: (id: number) => void;
  onNewSession: () => void;
  isCreating: boolean;
}

function ChatSessionSidebar({
  sessions,
  isLoading,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onNewSession,
  isCreating,
}: ChatSessionSidebarProps) {
  return (
    <Box
      sx={{
        width: 260,
        borderRight: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
      }}
    >
      <Box sx={{ p: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Conversations
        </Typography>
        <Tooltip title="New conversation">
          <span>
            <IconButton
              size="small"
              color="primary"
              onClick={onNewSession}
              disabled={isCreating}
            >
              {isCreating ? (
                <CircularProgress size={16} />
              ) : (
                <AddIcon fontSize="small" />
              )}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
      <Divider />
      <List dense sx={{ flex: 1, overflowY: 'auto' }}>
        {isLoading && (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <CircularProgress size={20} />
          </Box>
        )}
        {sessions.map((s) => (
          <ListItemButton
            key={s.id}
            selected={s.id === activeSessionId}
            onClick={() => onSelectSession(s.id)}
          >
            <ListItemText
              primary={s.title || `Chat #${s.id}`}
              secondary={`${s.message_count} messages`}
              slotProps={{ primary: { noWrap: true, variant: 'body2', sx: { fontWeight: 500 } } }}
            />
            <IconButton
              size="small"
              edge="end"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteSession(s.id);
              }}
            >
              <DeleteOutlined fontSize="small" />
            </IconButton>
          </ListItemButton>
        ))}
      </List>
    </Box>
  );
}

// Local icon import needed inside component scope
import { DeleteOutlined } from '@mui/icons-material';
