import {
  AccountBalance as BankIcon,
  ArrowDownward as DepositIcon,
  ArrowUpward as WithdrawIcon,
  Chat as ChatIcon,
  CurrencyExchange as EndorsementIcon,
  SwapHoriz as TransferIcon,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { bankingApi } from '../../api/banking';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import { useChatStore } from '../../store/chatStore';
import { StaffDashboardPage } from './StaffDashboardPage';

export function DashboardPage() {
  const { user, workspace } = useAuthStore();
  const isStaffRole = Boolean(user && ['manager', 'admin', 'superadmin'].includes(user.role));

  if (isStaffRole && workspace === 'staff') {
    return <StaffDashboardPage />;
  }

  return <PersonalDashboard />;
}

function PersonalDashboard() {
  const { user, accessToken } = useAuthStore();
  const openExpandedChat = useChatStore((s) => s.openExpanded);
  const navigate = useNavigate();

  const {
    data: account,
    isLoading: accountLoading,
    isError: noAccount,
  } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  const { data: txnsData } = useQuery({
    queryKey: ['recent-transactions', 'mine', user?.id],
    queryFn: () => bankingApi.getTransactions({ scope: 'mine', page: 1 }),
    enabled: Boolean(user?.id && accessToken && account),
  });

  return (
    <Stack spacing={3}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="h4">Welcome, {user?.first_name || user?.username}</Typography>
          <Typography variant="body2" color="text.secondary">
            Personal Banking Dashboard &middot; {user?.email}
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<ChatIcon />} onClick={openExpandedChat}>
          Open Assistant
        </Button>
      </Box>

      {accountLoading ? (
        <CircularProgress size={28} />
      ) : account ? (
        <>
          {!account.is_active && (
            <Alert severity="error">
              Your personal bank account ({account.account_number}) is currently frozen. Deposits,
              withdrawals, and transfers are disabled until reactivated by a branch manager.
            </Alert>
          )}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
              gap: 2.5,
            }}
          >
            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    Available Balance
                  </Typography>
                  <BankIcon color="primary" fontSize="small" />
                </Stack>
                <Typography variant="h4" color="primary" sx={{ fontWeight: 700 }}>
                  ${Number(account.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {account.account_number} &middot; {account.account_type.toUpperCase()}
                </Typography>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    USD Endorsement Status
                  </Typography>
                  <EndorsementIcon color="secondary" fontSize="small" />
                </Stack>
                <Typography variant="h5" sx={{ fontWeight: 700 }}>
                  {account.is_usd_endorsed ? 'Approved' : 'Not Endorsed'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {account.is_usd_endorsed
                    ? `Limit: $${Number(account.usd_endorsement_limit).toLocaleString()}`
                    : 'Request USD endorsement under Endorsements'}
                </Typography>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Quick Actions
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<DepositIcon />}
                    disabled={!account.is_active}
                    onClick={() => navigate('/banking/deposit')}
                  >
                    Deposit
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<WithdrawIcon />}
                    disabled={!account.is_active}
                    onClick={() => navigate('/banking/withdraw')}
                  >
                    Withdraw
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<TransferIcon />}
                    disabled={!account.is_active}
                    onClick={() => navigate('/banking/transfer')}
                  >
                    Transfer
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          </Box>
        </>
      ) : (
        noAccount && (
          <Alert severity="info">
            No personal bank account is attached to this profile.
          </Alert>
        )
      )}

      {account && (
        <Card>
          <CardContent>
            <Stack
              direction="row"
              sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
            >
              <Typography variant="h6">Recent Personal Transactions</Typography>
              <Button size="small" onClick={() => navigate('/banking/transactions')}>
                View All
              </Button>
            </Stack>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Reference</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Channel</TableCell>
                    <TableCell>Description</TableCell>
                    <TableCell align="right">Amount</TableCell>
                    <TableCell align="right">Balance After</TableCell>
                    <TableCell>Date</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(txnsData?.results ?? []).slice(0, 6).map((t) => (
                    <TableRow key={t.id}>
                      <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        {t.reference}
                      </TableCell>
                      <TableCell>
                        <StatusChip value={t.transaction_type} />
                      </TableCell>
                      <TableCell>
                        <StatusChip value={t.channel} />
                      </TableCell>
                      <TableCell>{t.description || '-'}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        ${Number(t.amount).toFixed(2)}
                      </TableCell>
                      <TableCell align="right">${Number(t.balance_after).toFixed(2)}</TableCell>
                      <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                  {(txnsData?.results ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        No transactions found.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </Box>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
