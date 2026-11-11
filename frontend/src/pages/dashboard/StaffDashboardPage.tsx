import {
  AccountBalance as BankIcon,
  Chat as ChatIcon,
  FactCheck as ApprovalIcon,
  Groups as CustomersIcon,
  ReceiptLong as TransactionsIcon,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Link,
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

export function StaffDashboardPage() {
  const { user, accessToken, setWorkspace } = useAuthStore();
  const openExpandedChat = useChatStore((s) => s.openExpanded);
  const navigate = useNavigate();

  const { data: summary, isLoading } = useQuery({
    queryKey: ['staff-dashboard', user?.id],
    queryFn: bankingApi.getStaffDashboard,
    enabled: Boolean(user?.id && accessToken),
  });

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

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
          <Typography variant="h4">Back-Office Operations</Typography>
          <Typography variant="body2" color="text.secondary">
            Signed in as {user?.first_name || user?.username} &middot; Role:{' '}
            {user?.role.toUpperCase()} &middot; {user?.email}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5}>
          <Button
            variant="contained"
            startIcon={<CustomersIcon />}
            onClick={() => navigate('/staff/customers')}
          >
            Customer Directory
          </Button>
          <Button variant="outlined" startIcon={<ChatIcon />} onClick={openExpandedChat}>
            Open Assistant
          </Button>
        </Stack>
      </Box>

      {user?.bank_account && (
        <Alert
          severity="info"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => {
                setWorkspace('personal');
                navigate('/dashboard');
              }}
            >
              Open Personal Account
            </Button>
          }
        >
          Your user also holds a personal customer account ({user.bank_account.account_number},{' '}
          ${Number(user.bank_account.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}).
          Switch to the Personal workspace to manage your own funds.
        </Alert>
      )}

      {summary && (
        <>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                sm: 'repeat(2, 1fr)',
                lg: 'repeat(4, 1fr)',
              },
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
                    Total Bank Liquidity
                  </Typography>
                  <BankIcon color="primary" fontSize="small" />
                </Stack>
                <Typography variant="h4" color="primary" sx={{ fontWeight: 700 }}>
                  ${Number(summary.total_liquidity).toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                  })}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {summary.active_accounts} active &middot; {summary.frozen_accounts} frozen accounts
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
                    Account Holders
                  </Typography>
                  <CustomersIcon color="secondary" fontSize="small" />
                </Stack>
                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                  {summary.total_customers}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {summary.usd_endorsed_accounts} USD-endorsed accounts
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
                    Pending Approvals
                  </Typography>
                  <ApprovalIcon color="warning" fontSize="small" />
                </Stack>
                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                  {summary.pending_cheques + summary.pending_endorsements}
                </Typography>
                <Stack direction="row" spacing={1.5} sx={{ mt: 0.5 }}>
                  <Link
                    component="button"
                    variant="caption"
                    underline="hover"
                    onClick={() => navigate('/admin/cheque-requests')}
                  >
                    Cheques: {summary.pending_cheques}
                  </Link>
                  <Link
                    component="button"
                    variant="caption"
                    underline="hover"
                    onClick={() => navigate('/admin/endorsements')}
                  >
                    USD Endorsements: {summary.pending_endorsements}
                  </Link>
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1 }}
                >
                  <Typography variant="body2" color="text.secondary">
                    Total Transactions
                  </Typography>
                  <TransactionsIcon color="action" fontSize="small" />
                </Stack>
                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                  {summary.total_transactions}
                </Typography>
                <Link
                  component="button"
                  variant="caption"
                  underline="hover"
                  onClick={() => navigate('/staff/transactions')}
                >
                  Inspect Ledger
                </Link>
              </CardContent>
            </Card>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', xl: '3fr 2fr' },
              gap: 3,
              alignItems: 'start',
            }}
          >
            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
                >
                  <Typography variant="h6">Recent Customer Transactions</Typography>
                  <Button size="small" onClick={() => navigate('/staff/transactions')}>
                    View All
                  </Button>
                </Stack>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Customer</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Channel</TableCell>
                        <TableCell align="right">Amount</TableCell>
                        <TableCell align="right">Balance After</TableCell>
                        <TableCell>Date</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {summary.recent_transactions.map((t) => (
                        <TableRow key={t.id} hover>
                          <TableCell>
                            <Link
                              component="button"
                              variant="body2"
                              underline="hover"
                              sx={{ fontWeight: 600 }}
                              onClick={() => navigate(`/staff/customers/${t.user_id}`)}
                            >
                              {t.username}
                            </Link>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              {t.account_number}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <StatusChip value={t.transaction_type} />
                          </TableCell>
                          <TableCell>
                            <StatusChip value={t.channel} />
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 600 }}>
                            ${Number(t.amount).toFixed(2)}
                          </TableCell>
                          <TableCell align="right">${Number(t.balance_after).toFixed(2)}</TableCell>
                          <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                        </TableRow>
                      ))}
                      {summary.recent_transactions.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                            No transactions recorded yet.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </Box>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
                >
                  <Typography variant="h6">Recent Audit Activities</Typography>
                  <Button size="small" onClick={() => navigate('/staff/activities')}>
                    View All
                  </Button>
                </Stack>
                <Stack spacing={1.5}>
                  {summary.recent_activities.map((act) => (
                    <Box
                      key={act.id}
                      sx={{
                        p: 1.25,
                        border: '1px solid #e2e8f0',
                        borderRadius: 1.5,
                        bgcolor: '#fafafa',
                      }}
                    >
                      <Stack
                        direction="row"
                        sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}
                      >
                        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                          <StatusChip value={act.category} />
                          <Typography variant="caption" sx={{ fontWeight: 700 }}>
                            {act.action}
                          </Typography>
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {new Date(act.created_at).toLocaleTimeString()}
                        </Typography>
                      </Stack>
                      <Typography variant="body2">{act.description}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Subject:{' '}
                        <Link
                          component="button"
                          variant="caption"
                          underline="hover"
                          onClick={() => navigate(`/staff/customers/${act.subject_user}`)}
                        >
                          {act.subject_username}
                        </Link>
                        {act.actor_username ? ` · Actor: ${act.actor_username}` : ''}
                      </Typography>
                    </Box>
                  ))}
                  {summary.recent_activities.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                      No activity events recorded yet.
                    </Typography>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Box>
        </>
      )}
    </Stack>
  );
}

