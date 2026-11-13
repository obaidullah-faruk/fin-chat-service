import { useEffect, useRef, useState } from 'react';
import {
  Add as AddIcon,
  BuildOutlined as ToolIcon,
  Chat as ChatIcon,
  CloseFullscreen as RestoreIcon,
  DeleteOutlined as DeleteIcon,
  OpenInFull as MaximizeIcon,
  PsychologyOutlined as BrainIcon,
  Remove as MinimizeIcon,
  SecurityOutlined as ShieldIcon,
  Send as SendIcon,
  SmartToy as BotIcon,
  Wifi as WifiIcon,
  WifiOff as WifiOffIcon,
} from '@mui/icons-material';
import {
  Box,
  CircularProgress,
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
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { chatApi, getChatWebSocketUrl } from '../../api/chat';
import { useAuthStore } from '../../store/authStore';
import { useChatStore } from '../../store/chatStore';
import type { ChatMessage, StreamEvent } from '../../types';

interface ToolStatusState {
  stage: string;
  message: string;
  toolName?: string;
}

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
  const [toolStatus, setToolStatus] = useState<ToolStatusState | null>(null);
  const [streamingTokens, setStreamingTokens] = useState<string>('');
  const [optimisticUserMsg, setOptimisticUserMsg] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const isOpen = mode !== 'collapsed';

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

  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', activeSessionId, user?.id],
    queryFn: () => chatApi.getMessages(activeSessionId!),
    enabled: Boolean(accessToken && user && isOpen && activeSessionId !== null),
  });

  // WebSocket streaming connection manager
  useEffect(() => {
    if (!isOpen || !activeSessionId || !accessToken) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      return;
    }

    const wsUrl = getChatWebSocketUrl(activeSessionId, accessToken);
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
    } catch (err) {
      console.warn('Failed to open WebSocket:', err);
      setWsConnected(false);
      return;
    }

    ws.onopen = () => {
      setWsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data: StreamEvent = JSON.parse(event.data);
        if (data.type === 'status') {
          setToolStatus({
            stage: data.stage,
            message: data.message,
            toolName: undefined,
          });
        } else if (data.type === 'tool_call_start') {
          setToolStatus({
            stage: 'tool',
            message: data.message,
            toolName: data.tool_name,
          });
        } else if (data.type === 'tool_call_end') {
          // Status kept until next state or tokens arrive
        } else if (data.type === 'token') {
          setToolStatus(null);
          setStreamingTokens((prev) => prev + data.token);
        } else if (data.type === 'done') {
          setToolStatus(null);
          setStreamingTokens('');
          setOptimisticUserMsg(null);
          queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
          queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSessionId] });
        } else if (data.type === 'error') {
          setToolStatus({
            stage: 'error',
            message: data.error || 'AI processing encountered an issue.',
          });
          setTimeout(() => {
            setToolStatus(null);
            setStreamingTokens('');
            setOptimisticUserMsg(null);
            queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSessionId] });
          }, 3500);
        }
      } catch {
        // Ignored unformatted text
      }
    };

    ws.onerror = () => {
      setWsConnected(false);
    };

    ws.onclose = () => {
      setWsConnected(false);
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      setWsConnected(false);
    };
  }, [isOpen, activeSessionId, accessToken, queryClient]);

  // Auto-scroll on new messages, streaming tokens, or status updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, mode, streamingTokens, toolStatus, optimisticUserMsg]);

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
      if (activeSessionId === deletedId) {
        setActiveSessionId(null);
      }
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: async (text: string) => {
      let targetSessionId = activeSessionId;
      if (!targetSessionId) {
        const newSession = await chatApi.createSession('');
        targetSessionId = newSession.id;
        setActiveSessionId(targetSessionId);
      }
      const res = await chatApi.sendMessage(targetSessionId, text);
      return { targetSessionId, res };
    },
    onSuccess: ({ targetSessionId }) => {
      setOptimisticUserMsg(null);
      setToolStatus(null);
      setStreamingTokens('');
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['chat-messages', targetSessionId] });
    },
    onError: () => {
      setOptimisticUserMsg(null);
      setToolStatus(null);
      setStreamingTokens('');
    },
  });

  if (!accessToken || !user) {
    return null;
  }

  const isSending = sendMessageMutation.isPending || Boolean(optimisticUserMsg);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isSending) return;
    setInput('');

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

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      setOptimisticUserMsg(trimmed);
      setStreamingTokens('');
      setToolStatus({
        stage: 'init',
        message: 'Connecting to FinChat banking sub-agents...',
      });
      wsRef.current.send(JSON.stringify({ content: trimmed }));
    } else {
      setOptimisticUserMsg(trimmed);
      setToolStatus({
        stage: 'init',
        message: 'Contacting FinChat AI Service...',
      });
      sendMessageMutation.mutate(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const getStatusIcon = (stage: string) => {
    if (stage.includes('pii')) return <ShieldIcon sx={{ fontSize: 16, color: '#059669' }} />;
    if (stage.includes('tool')) return <ToolIcon sx={{ fontSize: 16, color: '#d97706' }} />;
    if (stage.includes('rout')) return <BrainIcon sx={{ fontSize: 16, color: '#4f46e5' }} />;
    return <CircularProgress size={14} thickness={5} sx={{ color: '#4f46e5' }} />;
  };

  const renderStatusPill = () => {
    if (!toolStatus) return null;
    const isError = toolStatus.stage === 'error';

    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-start', my: 0.5 }}>
        <Paper
          elevation={0}
          sx={{
            px: 1.5,
            py: 0.75,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 1,
            bgcolor: isError ? '#fef2f2' : '#f0fdf4',
            border: isError ? '1px solid #fecaca' : '1px solid #bbf7d0',
            borderRadius: 2,
            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          }}
        >
          {isError ? (
            <CircularProgress size={14} color="error" />
          ) : (
            getStatusIcon(toolStatus.stage)
          )}
          <Typography
            variant="caption"
            sx={{
              color: isError ? '#b91c1c' : '#15803d',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
            }}
          >
            {toolStatus.message}
            {toolStatus.toolName && (
              <Box
                component="code"
                sx={{
                  bgcolor: '#e2e8f0',
                  color: '#1e293b',
                  px: 0.5,
                  py: 0.2,
                  borderRadius: 0.5,
                  fontSize: '0.7rem',
                  fontFamily: 'monospace',
                }}
              >
                {toolStatus.toolName}
              </Box>
            )}
          </Typography>
        </Paper>
      </Box>
    );
  };

  const renderStreamingBubble = () => {
    if (!streamingTokens) return null;

    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-start' }}>
        <Paper
          elevation={0}
          sx={{
            px: 1.75,
            py: 1,
            maxWidth: '82%',
            bgcolor: 'background.paper',
            color: 'text.primary',
            border: '1px solid #c7d2fe',
            borderRadius: 2,
            boxShadow: '0 1px 4px rgba(79, 70, 229, 0.08)',
          }}
        >
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {streamingTokens}
            <Box
              component="span"
              sx={{
                display: 'inline-block',
                width: '6px',
                height: '14px',
                bgcolor: 'primary.main',
                ml: 0.5,
                verticalAlign: 'middle',
                animation: 'blink 0.8s infinite',
                '@keyframes blink': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0 },
                },
              }}
            />
          </Typography>
        </Paper>
      </Box>
    );
  };

  const renderOptimisticUserMessage = () => {
    if (!optimisticUserMsg) return null;

    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Paper
          elevation={0}
          sx={{
            px: 1.75,
            py: 1,
            maxWidth: '82%',
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            borderRadius: 2,
            opacity: 0.92,
          }}
        >
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {optimisticUserMsg}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              display: 'block',
              mt: 0.5,
              opacity: 0.75,
              fontSize: '0.65rem',
              textAlign: 'right',
            }}
          >
            Sending...
          </Typography>
        </Paper>
      </Box>
    );
  };

  const renderMessageList = () => (
    <Box
      sx={{
        flex: 1,
        overflowY: 'auto',
        p: 2,
        bgcolor: '#f8fafc',
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
      }}
    >
      {messagesLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={24} />
        </Box>
      )}
      {!messagesLoading && messages.length === 0 && !optimisticUserMsg && (
        <Box sx={{ textAlign: 'center', py: 5, px: 2, color: 'text.secondary' }}>
          <BotIcon sx={{ fontSize: 40, color: 'primary.light', mb: 1 }} />
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            FinChat Banking Assistant
          </Typography>
          <Typography variant="body2">
            Ask about your balance, recent transactions, statement, or banking services.
          </Typography>
        </Box>
      )}
      {messages.map((msg: ChatMessage) => {
        const isUser = msg.role === 'user';
        return (
          <Box
            key={msg.id}
            sx={{
              display: 'flex',
              justifyContent: isUser ? 'flex-end' : 'flex-start',
            }}
          >
            <Paper
              elevation={0}
              sx={{
                px: 1.75,
                py: 1,
                maxWidth: '82%',
                bgcolor: isUser ? 'primary.main' : 'background.paper',
                color: isUser ? 'primary.contrastText' : 'text.primary',
                border: isUser ? 'none' : '1px solid #e2e8f0',
                borderRadius: 2,
              }}
            >
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {msg.content}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mt: 0.5,
                  opacity: 0.7,
                  fontSize: '0.65rem',
                  textAlign: 'right',
                }}
              >
                {new Date(msg.created_at).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </Typography>
            </Paper>
          </Box>
        );
      })}

      {renderOptimisticUserMessage()}
      {renderStatusPill()}
      {renderStreamingBubble()}

      <div ref={messagesEndRef} />
    </Box>
  );

  const renderInputBar = () => (
    <Box
      sx={{
        p: 1.5,
        borderTop: '1px solid #e2e8f0',
        bgcolor: 'background.paper',
        display: 'flex',
        gap: 1,
        alignItems: 'flex-end',
      }}
    >
      <TextField
        fullWidth
        size="small"
        multiline
        maxRows={3}
        placeholder="Type a banking request (e.g. 'What is my balance?')..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isSending}
      />
      <IconButton
        color="primary"
        onClick={handleSend}
        disabled={!input.trim() || isSending}
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          '&:hover': { bgcolor: 'primary.dark' },
          '&.Mui-disabled': { bgcolor: 'action.disabledBackground' },
        }}
      >
        {isSending ? (
          <CircularProgress size={20} color="inherit" />
        ) : (
          <SendIcon fontSize="small" />
        )}
      </IconButton>
    </Box>
  );

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
              '& .MuiPaper-root': {
                borderRadius: 0,
              },
            },
          },
        }}
      >
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
            <BotIcon />
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              FinChat Assistant
            </Typography>
            <Tooltip title={wsConnected ? 'Live streaming connected' : 'Connecting to live stream...'}>
              {wsConnected ? (
                <WifiIcon sx={{ fontSize: 16, color: '#86efac' }} />
              ) : (
                <WifiOffIcon sx={{ fontSize: 16, color: 'rgba(255,255,255,0.6)' }} />
              )}
            </Tooltip>
          </Stack>
          <Stack direction="row" spacing={0.5}>
            <Tooltip title="Restore floating panel">
              <IconButton size="small" color="inherit" onClick={openExpanded}>
                <RestoreIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Minimize">
              <IconButton size="small" color="inherit" onClick={collapse}>
                <MinimizeIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        <Box sx={{ display: 'flex', flex: 1, minHeight: 0 }}>
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
                <IconButton
                  size="small"
                  color="primary"
                  onClick={() => createSessionMutation.mutate()}
                  disabled={createSessionMutation.isPending}
                >
                  <AddIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
            <Divider />
            <List dense sx={{ flex: 1, overflowY: 'auto' }}>
              {sessionsLoading && (
                <Box sx={{ p: 2, textAlign: 'center' }}>
                  <CircularProgress size={20} />
                </Box>
              )}
              {sessions.map((s) => (
                <ListItemButton
                  key={s.id}
                  selected={s.id === activeSessionId}
                  onClick={() => setActiveSessionId(s.id)}
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
                      deleteSessionMutation.mutate(s.id);
                    }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </ListItemButton>
              ))}
            </List>
          </Box>

          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {renderMessageList()}
            {renderInputBar()}
          </Box>
        </Box>
      </Dialog>
    );
  }

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
          <BotIcon fontSize="small" />
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            FinChat Assistant
          </Typography>
          <Tooltip title={wsConnected ? 'Live streaming connected' : 'Connecting to live stream...'}>
            {wsConnected ? (
              <WifiIcon sx={{ fontSize: 16, color: '#86efac' }} />
            ) : (
              <WifiOffIcon sx={{ fontSize: 16, color: 'rgba(255,255,255,0.6)' }} />
            )}
          </Tooltip>
        </Stack>
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="New chat">
            <IconButton
              size="small"
              color="inherit"
              onClick={() => createSessionMutation.mutate()}
              disabled={createSessionMutation.isPending}
            >
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Expand full view">
            <IconButton size="small" color="inherit" onClick={openMaximized}>
              <MaximizeIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Minimize">
            <IconButton size="small" color="inherit" onClick={collapse}>
              <MinimizeIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>

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

      {renderMessageList()}
      {renderInputBar()}
    </Paper>
  );
}
