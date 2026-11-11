import { useEffect, useRef, useState } from 'react';
import {
  Add as AddIcon,
  Chat as ChatIcon,
  CloseFullscreen as RestoreIcon,
  DeleteOutlined as DeleteIcon,
  OpenInFull as MaximizeIcon,
  Remove as MinimizeIcon,
  Send as SendIcon,
  SmartToy as BotIcon,
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
import { chatApi } from '../../api/chat';
import { useAuthStore } from '../../store/authStore';
import { useChatStore } from '../../store/chatStore';
import type { ChatMessage } from '../../types';

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, mode]);

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
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['chat-messages', targetSessionId] });
    },
  });

  if (!accessToken || !user) {
    return null;
  }

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || sendMessageMutation.isPending) return;
    setInput('');
    sendMessageMutation.mutate(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
      {!messagesLoading && messages.length === 0 && (
        <Box sx={{ textAlign: 'center', py: 5, px: 2, color: 'text.secondary' }}>
          <BotIcon sx={{ fontSize: 40, color: 'primary.light', mb: 1 }} />
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            FinChat Assistant
          </Typography>
          <Typography variant="body2">
            Ask a question or test sending a message. Try asking &quot;What is my balance?&quot;.
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
        placeholder="Type a message..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={sendMessageMutation.isPending}
      />
      <IconButton
        color="primary"
        onClick={handleSend}
        disabled={!input.trim() || sendMessageMutation.isPending}
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          '&:hover': { bgcolor: 'primary.dark' },
          '&.Mui-disabled': { bgcolor: 'action.disabledBackground' },
        }}
      >
        {sendMessageMutation.isPending ? (
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
            zIndex: 1300,
            boxShadow: 4,
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
        open
        onClose={collapse}
        fullWidth
        maxWidth="lg"
        slotProps={{
          paper: {
            sx: {
              height: '85vh',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
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
        width: 400,
        height: 580,
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

