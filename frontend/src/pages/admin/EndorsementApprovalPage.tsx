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
import { getApiErrorMessage } from '../../api/client';
import { endorsementApi } from '../../api/endorsement';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import type { Endorsement, EndorsementStatus } from '../../types';

export function EndorsementApprovalPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user: currentUser, accessToken } = useAuthStore();
  const [statusFilter, setStatusFilter] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [reviewTarget, setReviewTarget] = useState<{
    item: Endorsement;
    nextStatus: Extract<EndorsementStatus, 'approved' | 'rejected'>;
  } | null>(null);
  const [remarks, setRemarks] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['admin-endorsements', statusFilter, currentUser?.id],
    queryFn: () => endorsementApi.getEndorsements({ status: statusFilter || undefined }),
    enabled: Boolean(currentUser?.id && accessToken),
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      endorsementApi.reviewEndorsement(reviewTarget!.item.id, {
        status: reviewTarget!.nextStatus,
        review_remarks: remarks,
      }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['admin-endorsements'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard-endorsements'] });
      queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
      setReviewTarget(null);
      setRemarks('');
      setFeedback({
        type: 'success',
        text: `USD endorsement #${updated.id} ${updated.status}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4">USD Endorsement Approvals</Typography>

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
                    <TableCell>Type</TableCell>
                    <TableCell align="right">USD Limit</TableCell>
                    <TableCell>Passport</TableCell>
                    <TableCell>Notes</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data?.results ?? []).map((item) => {
                    const isSelfRequest = currentUser?.id === item.requester;
                    return (
                      <TableRow key={item.id} hover>
                        <TableCell>#{item.id}</TableCell>
                        <TableCell>
                          <Link
                            component="button"
                            variant="body2"
                            underline="hover"
                            sx={{ fontWeight: 600 }}
                            onClick={() => navigate(`/staff/customers/${item.requester}`)}
                          >
                            {item.requester_username}
                          </Link>
                        </TableCell>
                        <TableCell>{item.account_number || '-'}</TableCell>
                        <TableCell>{item.endorsement_type.replace(/_/g, ' ').toUpperCase()}</TableCell>
                        <TableCell align="right">
                          {item.amount ? `$${Number(item.amount).toLocaleString()}` : '-'}
                        </TableCell>
                        <TableCell>{item.passport_number || '-'}</TableCell>
                        <TableCell>{item.notes || '-'}</TableCell>
                        <TableCell>
                          <StatusChip value={item.status} />
                        </TableCell>
                        <TableCell align="right">
                          {isSelfRequest ? (
                            <Chip size="small" label="Own Request (SoD)" variant="outlined" />
                          ) : (
                            item.status === 'pending' && (
                              <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
                                <Button
                                  size="small"
                                  variant="contained"
                                  color="success"
                                  onClick={() => {
                                    setReviewTarget({ item, nextStatus: 'approved' });
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
                                    setReviewTarget({ item, nextStatus: 'rejected' });
                                    setRemarks('');
                                  }}
                                >
                                  Reject
                                </Button>
                              </Stack>
                            )
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {(data?.results ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={9} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                        No endorsement requests found.
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
          {reviewTarget?.nextStatus.toUpperCase()} Endorsement #{reviewTarget?.item.id}
        </DialogTitle>
        <DialogContent>
          <TextField
            label="Review Remarks"
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
