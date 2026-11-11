import { useState } from 'react';
import {
  AccountBalanceWallet as TellerDepositIcon,
  ArrowBack as BackIcon,
  Edit as EditIcon,
  Lock as FreezeIcon,
  LockOpen as UnfreezeIcon,
  MoneyOff as TellerWithdrawIcon,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Pagination,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { bankingApi } from '../../api/banking';
import { chequeApi } from '../../api/cheque';
import { getApiErrorMessage } from '../../api/client';
import { endorsementApi } from '../../api/endorsement';
import { usersApi } from '../../api/users';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import type { ChequeBookRequest, ChequeStatus, Endorsement, EndorsementStatus } from '../../types';

export function CustomerDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const targetUserId = Number(userId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user: currentUser, accessToken } = useAuthStore();

  const [tab, setTab] = useState(0);
  const [txnPage, setTxnPage] = useState(1);
  const [txnTypeFilter, setTxnTypeFilter] = useState('');
  const [txnChannelFilter, setTxnChannelFilter] = useState('');
  const [actPage, setActPage] = useState(1);
  const [actCategoryFilter, setActCategoryFilter] = useState('');

  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [tellerDialog, setTellerDialog] = useState<'deposit' | 'withdraw' | null>(null);
  const [tellerAmount, setTellerAmount] = useState('');
  const [tellerDesc, setTellerDesc] = useState('');

  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [accountForm, setAccountForm] = useState<{
    account_type: 'savings' | 'current' | 'salary';
    is_active: boolean;
    reason: string;
  }>({ account_type: 'savings', is_active: true, reason: '' });

  const [chequeReview, setChequeReview] = useState<{
    req: ChequeBookRequest;
    nextStatus: Extract<ChequeStatus, 'approved' | 'rejected' | 'issued'>;
  } | null>(null);
  const [endorsementReview, setEndorsementReview] = useState<{
    item: Endorsement;
    nextStatus: Extract<EndorsementStatus, 'approved' | 'rejected'>;
  } | null>(null);
  const [reviewRemarks, setReviewRemarks] = useState('');

  const canFetch = Boolean(currentUser?.id && accessToken && Number.isFinite(targetUserId));

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ['customer-detail', targetUserId, currentUser?.id],
    queryFn: () => bankingApi.getCustomerDetail(targetUserId),
    enabled: canFetch,
  });

  const { data: txnsData, isLoading: txnsLoading } = useQuery({
    queryKey: [
      'customer-transactions',
      targetUserId,
      txnPage,
      txnTypeFilter,
      txnChannelFilter,
      currentUser?.id,
    ],
    queryFn: () =>
      bankingApi.getTransactions({
        scope: 'all',
        user_id: targetUserId,
        page: txnPage,
        transaction_type: txnTypeFilter || undefined,
        channel: txnChannelFilter || undefined,
      }),
    enabled: canFetch,
  });

  const { data: activitiesData, isLoading: activitiesLoading } = useQuery({
    queryKey: ['customer-activities', targetUserId, actPage, actCategoryFilter, currentUser?.id],
    queryFn: () =>
      usersApi.getActivities({
        subject_user: targetUserId,
        page: actPage,
        category: actCategoryFilter || undefined,
      }),
    enabled: canFetch,
  });

  const { data: chequesData } = useQuery({
    queryKey: ['customer-cheques', targetUserId, currentUser?.id],
    queryFn: () => chequeApi.getRequests({ user_id: targetUserId }),
    enabled: canFetch,
  });

  const { data: endorsementsData } = useQuery({
    queryKey: ['customer-endorsements', targetUserId, currentUser?.id],
    queryFn: () => endorsementApi.getEndorsements({ user_id: targetUserId }),
    enabled: canFetch,
  });

  const invalidateCustomerQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['customer-detail', targetUserId] });
    queryClient.invalidateQueries({ queryKey: ['customer-transactions', targetUserId] });
    queryClient.invalidateQueries({ queryKey: ['customer-activities', targetUserId] });
    queryClient.invalidateQueries({ queryKey: ['customer-cheques', targetUserId] });
    queryClient.invalidateQueries({ queryKey: ['customer-endorsements', targetUserId] });
    queryClient.invalidateQueries({ queryKey: ['staff-customers'] });
    queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
  };

  const tellerMutation = useMutation({
    mutationFn: () => {
      const payload = { amount: tellerAmount, description: tellerDesc };
      return tellerDialog === 'deposit'
        ? bankingApi.tellerDeposit(targetUserId, payload)
        : bankingApi.tellerWithdraw(targetUserId, payload);
    },
    onSuccess: (txn) => {
      invalidateCustomerQueries();
      setTellerDialog(null);
      setTellerAmount('');
      setTellerDesc('');
      setFeedback({
        type: 'success',
        text: `Branch teller ${txn.transaction_type} of $${Number(txn.amount).toFixed(
          2
        )} completed (Ref: ${txn.reference}). New balance: $${Number(txn.balance_after).toFixed(2)}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const accountMutation = useMutation({
    mutationFn: () => bankingApi.updateCustomerAccount(targetUserId, accountForm),
    onSuccess: (updated) => {
      invalidateCustomerQueries();
      setAccountDialogOpen(false);
      setFeedback({
        type: 'success',
        text: `Updated account ${updated.account_number} (${updated.account_type.toUpperCase()}, ${
          updated.is_active ? 'ACTIVE' : 'FROZEN'
        }).`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const chequeMutation = useMutation({
    mutationFn: () =>
      chequeApi.reviewRequest(chequeReview!.req.id, {
        status: chequeReview!.nextStatus,
        remarks: reviewRemarks,
      }),
    onSuccess: (updated) => {
      invalidateCustomerQueries();
      setChequeReview(null);
      setReviewRemarks('');
      setFeedback({
        type: 'success',
        text: `Cheque book request #${updated.id} updated to ${updated.status}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const endorsementMutation = useMutation({
    mutationFn: () =>
      endorsementApi.reviewEndorsement(endorsementReview!.item.id, {
        status: endorsementReview!.nextStatus,
        review_remarks: reviewRemarks,
      }),
    onSuccess: (updated) => {
      invalidateCustomerQueries();
      setEndorsementReview(null);
      setReviewRemarks('');
      setFeedback({
        type: 'success',
        text: `USD endorsement #${updated.id} ${updated.status}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !detail) {
    return (
      <Stack spacing={2}>
        <Button startIcon={<BackIcon />} onClick={() => navigate('/staff/customers')}>
          Back to Customers
        </Button>
        <Alert severity="error">Customer record not found or inaccessible.</Alert>
      </Stack>
    );
  }

  const { user, bank_account: account, addresses, stats } = detail;
  const isSelf = currentUser?.id === user.id;
  const fullName = `${user.first_name} ${user.last_name}`.trim() || user.username;
  const txnTotalPages = txnsData ? Math.max(1, Math.ceil(txnsData.count / 20)) : 1;
  const actTotalPages = activitiesData ? Math.max(1, Math.ceil(activitiesData.count / 20)) : 1;

  const openAccountDialog = (freezeOverride?: boolean) => {
    if (!account) return;
    setAccountForm({
      account_type: account.account_type,
      is_active: freezeOverride !== undefined ? freezeOverride : account.is_active,
      reason: '',
    });
    setAccountDialogOpen(true);
  };

  return (
    <Stack spacing={3}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}
      >
        <Box>
          <Button
            size="small"
            startIcon={<BackIcon />}
            onClick={() => navigate('/staff/customers')}
            sx={{ mb: 1 }}
          >
            All Customers
          </Button>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="h4">{fullName}</Typography>
            <StatusChip value={user.role} />
            {account && <StatusChip value={account.is_active ? 'active' : 'frozen'} />}
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            @{user.username} &middot; {user.email} &middot; {user.phone || 'No phone on file'} &middot;
            Joined {new Date(user.created_at).toLocaleDateString()}
          </Typography>
        </Box>
      </Stack>

      {isSelf && (
        <Alert severity="warning">
          <strong>Separation of Duties (SoD):</strong> You are inspecting your own personal customer
          account. Branch teller deposits/withdrawals, account status overrides, and cheque or USD
          endorsement approvals on your own account are blocked. Use the Personal workspace for
          self-service banking.
        </Alert>
      )}

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '5fr 4fr' },
          gap: 2.5,
        }}
      >
        <Card>
          <CardContent>
            <Stack
              direction="row"
              sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}
            >
              <Typography variant="h6">Bank Account & Teller Controls</Typography>
              {account && <StatusChip value={account.is_active ? 'active' : 'frozen'} />}
            </Stack>

            {account ? (
              <Stack spacing={2.5}>
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
                    gap: 2,
                  }}
                >
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Account Number
                    </Typography>
                    <Typography variant="h6" sx={{ fontFamily: 'monospace' }}>
                      {account.account_number}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Current Balance
                    </Typography>
                    <Typography variant="h5" color="primary" sx={{ fontWeight: 700 }}>
                      {account.currency}{' '}
                      {Number(account.balance).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                      })}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Account Type
                    </Typography>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      {account.account_type.toUpperCase()}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      USD Endorsement
                    </Typography>
                    <Typography variant="body1" sx={{ fontWeight: 500 }}>
                      {account.is_usd_endorsed
                        ? `Enabled (Limit: $${Number(account.usd_endorsement_limit).toLocaleString()})`
                        : 'Not Endorsed'}
                    </Typography>
                  </Box>
                </Box>

                <Divider />

                <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                  <Button
                    size="small"
                    variant="contained"
                    color="success"
                    startIcon={<TellerDepositIcon />}
                    disabled={isSelf || !account.is_active}
                    onClick={() => {
                      setTellerDialog('deposit');
                      setTellerAmount('');
                      setTellerDesc('');
                    }}
                  >
                    Teller Deposit
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    color="warning"
                    startIcon={<TellerWithdrawIcon />}
                    disabled={isSelf || !account.is_active}
                    onClick={() => {
                      setTellerDialog('withdraw');
                      setTellerAmount('');
                      setTellerDesc('');
                    }}
                  >
                    Teller Withdraw
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<EditIcon />}
                    disabled={isSelf}
                    onClick={() => openAccountDialog()}
                  >
                    Change Type
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    color={account.is_active ? 'error' : 'success'}
                    startIcon={account.is_active ? <FreezeIcon /> : <UnfreezeIcon />}
                    disabled={isSelf}
                    onClick={() => openAccountDialog(!account.is_active)}
                  >
                    {account.is_active ? 'Freeze Account' : 'Unfreeze Account'}
                  </Button>
                </Stack>
              </Stack>
            ) : (
              <Alert severity="info">This user has not opened a bank account yet.</Alert>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 2 }}>
              360° Financial & Activity Metrics
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 2,
              }}
            >
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Total Deposits
                </Typography>
                <Typography variant="subtitle1" color="success.main" sx={{ fontWeight: 700 }}>
                  ${Number(stats.total_deposits).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Total Withdrawals
                </Typography>
                <Typography variant="subtitle1" color="warning.main" sx={{ fontWeight: 700 }}>
                  ${Number(stats.total_withdrawals).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Transfers Received
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  ${Number(stats.total_transfers_in).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Transfers Sent
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  ${Number(stats.total_transfers_out).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Transactions / Activities
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {stats.transaction_count} txns &middot; {stats.activity_count} events
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Pending Reviews
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {stats.pending_cheques} cheque &middot; {stats.pending_endorsements} USD
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Box>

      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}>
          <Tabs
            value={tab}
            onChange={(_e, val) => setTab(val)}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label={`Transactions (${stats.transaction_count})`} />
            <Tab label={`Activities (${stats.activity_count})`} />
            <Tab label="Cheque Requests" />
            <Tab label="USD Endorsements" />
            <Tab label={`Profile & Addresses (${addresses.length})`} />
          </Tabs>
        </Box>

        <CardContent>
          {tab === 0 && (
            <Stack spacing={2}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  select
                  label="Transaction Type"
                  size="small"
                  value={txnTypeFilter}
                  onChange={(e) => {
                    setTxnTypeFilter(e.target.value);
                    setTxnPage(1);
                  }}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="">All Types</MenuItem>
                  <MenuItem value="deposit">Deposit</MenuItem>
                  <MenuItem value="withdrawal">Withdrawal</MenuItem>
                  <MenuItem value="transfer_in">Transfer In</MenuItem>
                  <MenuItem value="transfer_out">Transfer Out</MenuItem>
                </TextField>
                <TextField
                  select
                  label="Channel"
                  size="small"
                  value={txnChannelFilter}
                  onChange={(e) => {
                    setTxnChannelFilter(e.target.value);
                    setTxnPage(1);
                  }}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="">All Channels</MenuItem>
                  <MenuItem value="online">Online / Digital</MenuItem>
                  <MenuItem value="atm">ATM</MenuItem>
                  <MenuItem value="branch_teller">Branch Teller</MenuItem>
                  <MenuItem value="system">System / Opening</MenuItem>
                </TextField>
              </Stack>

              {txnsLoading ? (
                <CircularProgress size={24} />
              ) : (
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Reference</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Channel</TableCell>
                        <TableCell>Counterparty</TableCell>
                        <TableCell>Processed By</TableCell>
                        <TableCell>Description</TableCell>
                        <TableCell align="right">Amount</TableCell>
                        <TableCell align="right">Balance After</TableCell>
                        <TableCell>Timestamp</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(txnsData?.results ?? []).map((t) => (
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
                          <TableCell>
                            {t.related_account_number
                              ? `${t.related_account_number} (${t.related_username})`
                              : '-'}
                          </TableCell>
                          <TableCell>{t.performed_by_username || '-'}</TableCell>
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
                          <TableCell colSpan={9} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                            No transactions found.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </Box>
              )}

              {txnTotalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Pagination
                    count={txnTotalPages}
                    page={txnPage}
                    onChange={(_e, val) => setTxnPage(val)}
                  />
                </Box>
              )}
            </Stack>
          )}

          {tab === 1 && (
            <Stack spacing={2}>
              <Box>
                <TextField
                  select
                  label="Category"
                  size="small"
                  value={actCategoryFilter}
                  onChange={(e) => {
                    setActCategoryFilter(e.target.value);
                    setActPage(1);
                  }}
                  sx={{ minWidth: 190 }}
                >
                  <MenuItem value="">All Categories</MenuItem>
                  <MenuItem value="auth">Authentication</MenuItem>
                  <MenuItem value="banking">Banking</MenuItem>
                  <MenuItem value="cheque">Cheque Book</MenuItem>
                  <MenuItem value="endorsement">USD Endorsement</MenuItem>
                  <MenuItem value="profile">Profile & Address</MenuItem>
                  <MenuItem value="admin">Administration</MenuItem>
                </TextField>
              </Box>

              {activitiesLoading ? (
                <CircularProgress size={24} />
              ) : (
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Timestamp</TableCell>
                        <TableCell>Category</TableCell>
                        <TableCell>Action</TableCell>
                        <TableCell>Actor</TableCell>
                        <TableCell>Description</TableCell>
                        <TableCell>IP Address</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(activitiesData?.results ?? []).map((act) => (
                        <TableRow key={act.id}>
                          <TableCell>{new Date(act.created_at).toLocaleString()}</TableCell>
                          <TableCell>
                            <StatusChip value={act.category} />
                          </TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', fontWeight: 600 }}>
                            {act.action}
                          </TableCell>
                          <TableCell>
                            {act.actor_username ? (
                              <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
                                <Typography variant="body2">{act.actor_username}</Typography>
                                {act.actor_role && <StatusChip value={act.actor_role} />}
                              </Stack>
                            ) : (
                              'System'
                            )}
                          </TableCell>
                          <TableCell>{act.description}</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                            {act.ip_address || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                      {(activitiesData?.results ?? []).length === 0 && (
                        <TableRow>
                          <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                            No activity events recorded for this customer.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </Box>
              )}

              {actTotalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Pagination
                    count={actTotalPages}
                    page={actPage}
                    onChange={(_e, val) => setActPage(val)}
                  />
                </Box>
              )}
            </Stack>
          )}

          {tab === 2 && (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Leaves</TableCell>
                    <TableCell>Delivery Address</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Remarks</TableCell>
                    <TableCell>Requested</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(chequesData?.results ?? []).map((req) => (
                    <TableRow key={req.id}>
                      <TableCell>#{req.id}</TableCell>
                      <TableCell>{req.leaves_requested}</TableCell>
                      <TableCell>{req.delivery_address_snapshot || '-'}</TableCell>
                      <TableCell>
                        <StatusChip value={req.status} />
                      </TableCell>
                      <TableCell>{req.remarks || '-'}</TableCell>
                      <TableCell>{new Date(req.requested_at).toLocaleString()}</TableCell>
                      <TableCell align="right">
                        {isSelf ? (
                          <Chip size="small" label="Own Request (SoD)" variant="outlined" />
                        ) : (
                          <>
                            {req.status === 'pending' && (
                              <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                                <Button
                                  size="small"
                                  variant="contained"
                                  color="success"
                                  onClick={() => {
                                    setChequeReview({ req, nextStatus: 'approved' });
                                    setReviewRemarks('');
                                  }}
                                >
                                  Approve
                                </Button>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="error"
                                  onClick={() => {
                                    setChequeReview({ req, nextStatus: 'rejected' });
                                    setReviewRemarks('');
                                  }}
                                >
                                  Reject
                                </Button>
                              </Stack>
                            )}
                            {req.status === 'approved' && (
                              <Button
                                size="small"
                                variant="outlined"
                                onClick={() => {
                                  setChequeReview({ req, nextStatus: 'issued' });
                                  setReviewRemarks('Dispatched to customer address');
                                }}
                              >
                                Mark Issued
                              </Button>
                            )}
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {(chequesData?.results ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        No cheque book requests from this user.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </Box>
          )}

          {tab === 3 && (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell align="right">USD Limit</TableCell>
                    <TableCell>Passport</TableCell>
                    <TableCell>Notes</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Review Remarks</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(endorsementsData?.results ?? []).map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>#{item.id}</TableCell>
                      <TableCell>{item.endorsement_type.replace(/_/g, ' ').toUpperCase()}</TableCell>
                      <TableCell align="right">
                        {item.amount ? `$${Number(item.amount).toLocaleString()}` : '-'}
                      </TableCell>
                      <TableCell>{item.passport_number || '-'}</TableCell>
                      <TableCell>{item.notes || '-'}</TableCell>
                      <TableCell>
                        <StatusChip value={item.status} />
                      </TableCell>
                      <TableCell>{item.review_remarks || '-'}</TableCell>
                      <TableCell align="right">
                        {isSelf ? (
                          <Chip size="small" label="Own Request (SoD)" variant="outlined" />
                        ) : (
                          item.status === 'pending' && (
                            <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                              <Button
                                size="small"
                                variant="contained"
                                color="success"
                                onClick={() => {
                                  setEndorsementReview({ item, nextStatus: 'approved' });
                                  setReviewRemarks('');
                                }}
                              >
                                Approve
                              </Button>
                              <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                onClick={() => {
                                  setEndorsementReview({ item, nextStatus: 'rejected' });
                                  setReviewRemarks('');
                                }}
                              >
                                Reject
                              </Button>
                            </Stack>
                          )
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {(endorsementsData?.results ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        No USD endorsement requests from this user.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </Box>
          )}

          {tab === 4 && (
            <Stack spacing={3}>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
                  gap: 2,
                }}
              >
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Date of Birth
                  </Typography>
                  <Typography variant="body1">
                    {user.profile?.date_of_birth || 'Not provided'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    National ID / SSN
                  </Typography>
                  <Typography variant="body1">
                    {user.profile?.national_id || 'Not provided'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    User Status
                  </Typography>
                  <Box sx={{ mt: 0.5 }}>
                    <StatusChip value={user.is_active ? 'active' : 'inactive'} />
                  </Box>
                </Box>
              </Box>
              {user.profile?.bio && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Customer Bio / Notes
                  </Typography>
                  <Typography variant="body2">{user.profile.bio}</Typography>
                </Box>
              )}

              <Divider />

              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5 }}>
                  Registered Addresses
                </Typography>
                {addresses.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No addresses registered.
                  </Typography>
                ) : (
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' },
                      gap: 2,
                    }}
                  >
                    {addresses.map((addr) => (
                      <Box
                        key={addr.id}
                        sx={{
                          p: 2,
                          border: '1px solid',
                          borderColor: addr.is_primary ? 'primary.main' : '#e2e8f0',
                          borderRadius: 1.5,
                        }}
                      >
                        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.75 }}>
                          <StatusChip value={addr.label} />
                          {addr.is_primary && (
                            <Chip size="small" color="primary" label="Primary" />
                          )}
                        </Stack>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {addr.street}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {addr.city}, {addr.state} {addr.postal_code}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {addr.country}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
            </Stack>
          )}
        </CardContent>
      </Card>

      {/* Branch Teller Deposit / Withdraw Dialog */}
      <Dialog
        open={Boolean(tellerDialog)}
        onClose={() => setTellerDialog(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {tellerDialog === 'deposit' ? 'Branch Teller Deposit' : 'Branch Teller Withdrawal'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Customer: <strong>{fullName}</strong> ({account?.account_number})
            </Typography>
            <TextField
              label="Amount (USD)"
              type="number"
              slotProps={{ htmlInput: { step: '0.01', min: '0.01' } }}
              value={tellerAmount}
              onChange={(e) => setTellerAmount(e.target.value)}
              required
              fullWidth
            />
            <TextField
              label="Teller Note / Receipt Reference"
              multiline
              rows={2}
              value={tellerDesc}
              onChange={(e) => setTellerDesc(e.target.value)}
              placeholder={
                tellerDialog === 'deposit'
                  ? 'Counter cash deposit verified with ID'
                  : 'Counter cash withdrawal signed by customer'
              }
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTellerDialog(null)}>Cancel</Button>
          <Button
            variant="contained"
            color={tellerDialog === 'deposit' ? 'success' : 'warning'}
            disabled={tellerMutation.isPending || !tellerAmount}
            onClick={() => tellerMutation.mutate()}
          >
            {tellerMutation.isPending ? 'Processing...' : 'Confirm Operation'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Account Type / Freeze Dialog */}
      <Dialog
        open={accountDialogOpen}
        onClose={() => setAccountDialogOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>Manage Customer Account</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Account Type"
              value={accountForm.account_type}
              onChange={(e) =>
                setAccountForm({
                  ...accountForm,
                  account_type: e.target.value as 'savings' | 'current' | 'salary',
                })
              }
              fullWidth
            >
              <MenuItem value="savings">Savings</MenuItem>
              <MenuItem value="current">Current</MenuItem>
              <MenuItem value="salary">Salary</MenuItem>
            </TextField>
            <TextField
              select
              label="Account Status"
              value={accountForm.is_active ? 'active' : 'frozen'}
              onChange={(e) =>
                setAccountForm({ ...accountForm, is_active: e.target.value === 'active' })
              }
              fullWidth
            >
              <MenuItem value="active">Active (Operational)</MenuItem>
              <MenuItem value="frozen">Frozen (Block Debits & Credits)</MenuItem>
            </TextField>
            <TextField
              label="Audit Reason / Remarks"
              multiline
              rows={2}
              value={accountForm.reason}
              onChange={(e) => setAccountForm({ ...accountForm, reason: e.target.value })}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAccountDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={accountMutation.isPending}
            onClick={() => accountMutation.mutate()}
          >
            {accountMutation.isPending ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Cheque Review Dialog */}
      <Dialog
        open={Boolean(chequeReview)}
        onClose={() => setChequeReview(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {chequeReview?.nextStatus.toUpperCase()} Cheque Request #{chequeReview?.req.id}
        </DialogTitle>
        <DialogContent>
          <TextField
            label="Remarks"
            multiline
            rows={3}
            value={reviewRemarks}
            onChange={(e) => setReviewRemarks(e.target.value)}
            fullWidth
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChequeReview(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={chequeMutation.isPending}
            onClick={() => chequeMutation.mutate()}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>

      {/* Endorsement Review Dialog */}
      <Dialog
        open={Boolean(endorsementReview)}
        onClose={() => setEndorsementReview(null)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>
          {endorsementReview?.nextStatus.toUpperCase()} Endorsement #{endorsementReview?.item.id}
        </DialogTitle>
        <DialogContent>
          <TextField
            label="Review Remarks"
            multiline
            rows={3}
            value={reviewRemarks}
            onChange={(e) => setReviewRemarks(e.target.value)}
            fullWidth
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEndorsementReview(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={endorsementMutation.isPending}
            onClick={() => endorsementMutation.mutate()}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

