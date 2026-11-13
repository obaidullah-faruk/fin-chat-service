import { Send as SendIcon } from '@mui/icons-material';
import { Box, CircularProgress, IconButton, TextField } from '@mui/material';

interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
}

/**
 * Chat input bar with multiline text field and send button.
 */
export function ChatInputBar({ value, onChange, onSend, disabled }: ChatInputBarProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
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
        placeholder="Ask about balance, transactions, or banking services..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />
      <IconButton
        color="primary"
        onClick={onSend}
        disabled={!value.trim() || disabled}
        sx={{
          bgcolor: 'primary.main',
          color: 'white',
          '&:hover': { bgcolor: 'primary.dark' },
          '&.Mui-disabled': { bgcolor: 'action.disabledBackground' },
        }}
      >
        {disabled ? (
          <CircularProgress size={20} color="inherit" />
        ) : (
          <SendIcon fontSize="small" />
        )}
      </IconButton>
    </Box>
  );
}

