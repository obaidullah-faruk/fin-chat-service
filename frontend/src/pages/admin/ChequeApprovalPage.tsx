import { useState } from 'react';
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
  Link,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { chequeApi } from '../../api/cheque';
import { getApiErrorMessage } from '../../api/client';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import type { ChequeBookRequest, ChequeStatus } from '../../types';

export function ChequeApprovalPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user: currentUser, accessToken } = useAuthStore();
  const [statusFilter, setStatusFilter] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [reviewTarget, setReviewTarget] = useState<{
    req: ChequeBookRequest;
    nextStatus: Extract<ChequeStatus, 'approved' | 'rejected' | 'issued'>;
  } | null>(null);
  const [remarks, setRemarks] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['admin-cheque-requests', statusFilter, currentUser?.id],
    queryFn: () => chequeApi.getRequests({ status: statusFilter || undefined }),
    enabled: Boolean(currentUser?.id && accessToken),
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      chequeApi.reviewRequest(reviewTarget!.req.id, {
        status: reviewTarget!.nextStatus,
        remarks,
      }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['admin-cheque-requests'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-cheques'] });
      queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
      setReviewTarget(null);
      setRemarks('');
      setFeedback({
        type: 'success',
        text: `Cheque request #${updated.id} marked as ${updated.status}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4">Cheque Book Approvals</Typography>

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Box sx={{ mb: 2.5 }}>
            <TextField
              select
              label="Filter by Status"
              size="small"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="pending">Pending</MenuItem>
              <MenuItem value="approved">Approved</MenuItem>
              <MenuItem value="issued">Issued</MenuItem>
              <MenuItem value="rejected">Rejected</MenuItem>
            </TextField>
          </Box>

          {isLoading ? (
            <CircularProgress />
          ) : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Customer</TableCell>
                    <TableCell>Account</TableCell>
                    <TableCell>Leaves</TableCell>
                    <TableCell>Delivery Address</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Remarks</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data?.results ?? []).map((req) => {
                    const isSelfRequest = currentUser?.id === req.user;
                    return (
                      <TableRow key={req.id} hover>
                        <TableCell>#{req.id}</TableCell>
                        <TableCell>
                          <Link
                            component="button"
                            variant="body2"
                            underline="hover"
                            sx={{ fontWeight: 600 }}
                            onClick={() => navigate(`/staff/customers/${req.user}`)}
                          >
                            {req.username}
                          </Link>
                        </TableCell>
                        <TableCell>{req.account_number || '-'}</TableCell>
                        <TableCell>{req.leaves_requested}</TableCell>
                        <TableCell>{req.delivery_address_snapshot || '-'}</TableCell>
                        <TableCell>
                          <StatusChip value={req.status} />
                        </TableCell>
                        <TableCell>{req.remarks || '-'}</TableCell>
                        <TableCell align="right">
                          {isSelfRequest ? (
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
                                      setReviewTarget({ req, nextStatus: 'approved' });
                                      setRemarks('');
                                    }}
                                  >
                                    Approve
                                  </Button>
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    color="error"
                                    onClick={() => {
                                      setReviewTarget({ req, nextStatus: 'rejected' });
                                      setRemarks('');
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
                                    setReviewTarget({ req, nextStatus: 'issued' });
                                    setRemarks('Dispatched to customer address');
                                  }}
                                >
                                  Mark Issued
                                </Button>
                              )}
                            </>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {(data?.results ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={8} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        No cheque book requests found.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </Box>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(reviewTarget)} onClose={() => setReviewTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>
          {reviewTarget?.nextStatus.toUpperCase()} Request #{reviewTarget?.req.id}
        </DialogTitle>
        <DialogContent>
          <TextField
            label="Remarks"
            multiline
            rows={3}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            fullWidth
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReviewTarget(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={reviewMutation.isPending}
            onClick={() => reviewMutation.mutate()}
          >
            Confirm
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
