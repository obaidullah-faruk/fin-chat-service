import { SmartToy as BotIcon } from '@mui/icons-material';
import { Box, CircularProgress, Paper, Typography } from '@mui/material';
import type { ChatMessage } from '../../types';
import { ChatStatusPill, type StatusState } from './ChatStatusPill';
import { MarkdownContent } from './MarkdownContent';

interface StreamingCursorProps {
  tokens: string;
}

function StreamingBubble({ tokens }: StreamingCursorProps) {
  if (!tokens) return null;
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
        <Box sx={{ display: 'inline' }}>
          <MarkdownContent content={tokens} isUser={false} sx={{ display: 'inline' }} />
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
        </Box>
      </Paper>
    </Box>
  );
}

interface OptimisticMessageProps {
  content: string;
}

function OptimisticUserMessage({ content }: OptimisticMessageProps) {
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
          // Slightly dimmed to visually distinguish from confirmed messages
          opacity: 0.88,
        }}
      >
        <MarkdownContent content={content} isUser={true} />
        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 0.5, opacity: 0.7, fontSize: '0.65rem', textAlign: 'right' }}
        >
          {/* Message is dispatched – AI is now processing it */}
          Just now
        </Typography>
      </Paper>
    </Box>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  return (
    <Box sx={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
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
        <MarkdownContent content={message.content} isUser={isUser} />
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
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </Typography>
      </Paper>
    </Box>
  );
}

interface EmptyStateProps {
  visible: boolean;
}

function EmptyState({ visible }: EmptyStateProps) {
  if (!visible) return null;
  return (
    <Box sx={{ textAlign: 'center', py: 5, px: 2, color: 'text.secondary' }}>
      <BotIcon sx={{ fontSize: 40, color: 'primary.light', mb: 1 }} />
      <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
        FinChat Banking Assistant
      </Typography>
      <Typography variant="body2">
        Ask about your balance, recent transactions, statement, or banking services.
      </Typography>
    </Box>
  );
}

interface ChatMessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  optimisticUserMsg: string | null;
  streamingTokens: string;
  status: StatusState | null;
  bottomRef: React.RefObject<HTMLDivElement>;
}

/**
 * Renders the scrollable message list with loading, empty state,
 * history messages, optimistic user message, progress pill, and streaming bubble.
 */
export function ChatMessageList({
  messages,
  isLoading,
  optimisticUserMsg,
  streamingTokens,
  status,
  bottomRef,
}: ChatMessageListProps) {
  return (
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
      {isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={24} />
        </Box>
      )}

      <EmptyState
        visible={!isLoading && messages.length === 0 && !optimisticUserMsg}
      />

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {optimisticUserMsg && <OptimisticUserMessage content={optimisticUserMsg} />}
      <ChatStatusPill status={status} />
      <StreamingBubble tokens={streamingTokens} />

      <div ref={bottomRef} />
    </Box>
  );
}
