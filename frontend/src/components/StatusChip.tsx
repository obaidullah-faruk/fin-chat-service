import { Chip, ChipProps } from '@mui/material';

const COLOR_MAP: Record<string, ChipProps['color']> = {
  pending: 'warning',
  approved: 'success',
  issued: 'info',
  rejected: 'error',
  deposit: 'success',
  transfer_in: 'success',
  withdrawal: 'warning',
  transfer_out: 'info',
  superadmin: 'error',
  admin: 'secondary',
  manager: 'primary',
  customer: 'default',
  active: 'success',
  inactive: 'default',
  frozen: 'error',
  branch_teller: 'secondary',
  atm: 'primary',
  online: 'default',
  system: 'default',
  banking: 'primary',
  auth: 'default',
  cheque: 'info',
  endorsement: 'secondary',
  profile: 'default',
  usd_endorsed: 'success',
};

interface StatusChipProps {
  value: string;
  size?: ChipProps['size'];
}

export function StatusChip({ value, size = 'small' }: StatusChipProps) {
  const normalized = value.toLowerCase();
  const label = value.replace(/_/g, ' ').toUpperCase();
  return (
    <Chip
      label={label}
      color={COLOR_MAP[normalized] ?? 'default'}
      size={size}
      variant="outlined"
      sx={{ fontWeight: 600, fontSize: '0.7rem' }}
    />
  );
}
