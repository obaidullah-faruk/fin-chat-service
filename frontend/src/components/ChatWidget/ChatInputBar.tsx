import { Send as SendIcon } from '@mui/icons-material';
import { Box, CircularProgress, IconButton, TextField } from '@mui/material';

interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  isClosed?: boolean;
}

/**
 * Chat input bar with multiline text field and send button.
 */
export function ChatInputBar({
  value,
  onChange,
  onSend,
  disabled,
  isClosed = false,
}: ChatInputBarProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isClosed && !disabled) {
        onSend();
      }
    }
  };

  const isDisabled = disabled || isClosed;
  const placeholderText = isClosed
    ? 'This conversation is closed. Start a new chat to continue.'
    : 'Ask about balance, transactions, or banking services...';

  return (
    <Box
      sx={{
        p: 1.5,
        borderTop: '1px solid #e2e8f0',
        bgcolor: isClosed ? '#f8fafc' : 'background.paper',
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
        placeholder={placeholderText}
        value={isClosed ? '' : value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isDisabled}
      />
      <IconButton
        color="primary"
        onClick={onSend}
        disabled={!value.trim() || isDisabled}
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          '&:hover': { bgcolor: 'primary.dark' },
          '&.Mui-disabled': { bgcolor: 'action.disabledBackground' },
        }}
      >
        {disabled && !isClosed ? (
          <CircularProgress size={20} color="inherit" />
        ) : (
          <SendIcon fontSize="small" />
        )}
      </IconButton>
    </Box>
  );
}

