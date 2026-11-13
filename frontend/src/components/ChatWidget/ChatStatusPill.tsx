import {
  BuildOutlined as ToolIcon,
  PsychologyOutlined as BrainIcon,
  SecurityOutlined as ShieldIcon,
} from '@mui/icons-material';
import { Box, CircularProgress, Paper, Typography } from '@mui/material';
import { getStageCategory } from './chatUtils';

export interface StatusState {
  stage: string;
  message: string;
}

interface ChatStatusPillProps {
  status: StatusState | null;
}

function StageIcon({ stage }: { stage: string }) {
  const category = getStageCategory(stage);
  if (category === 'pii') return <ShieldIcon sx={{ fontSize: 16, color: '#059669' }} />;
  if (category === 'routing') return <BrainIcon sx={{ fontSize: 16, color: '#4f46e5' }} />;
  if (category === 'tool') return <ToolIcon sx={{ fontSize: 16, color: '#d97706' }} />;
  return <CircularProgress size={14} thickness={5} sx={{ color: '#4f46e5' }} />;
}

/**
 * Shows a progress/status pill during AI processing.
 * Only shows user-friendly messages – never raw tool names.
 */
export function ChatStatusPill({ status }: ChatStatusPillProps) {
  if (!status) return null;
  const isError = status.stage === 'error';

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
          <StageIcon stage={status.stage} />
        )}
        <Typography
          variant="caption"
          sx={{
            color: isError ? '#b91c1c' : '#15803d',
            fontWeight: 600,
          }}
        >
          {status.message}
        </Typography>
      </Paper>
    </Box>
  );
}

