import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/auth';
import { getApiErrorMessage } from '../../api/client';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';

export function ProfilePage() {
  const navigate = useNavigate();
  const { user, accessToken, setUser } = useAuthStore();
  const [firstName, setFirstName] = useState(user?.first_name ?? '');
  const [lastName, setLastName] = useState(user?.last_name ?? '');
  const [phone, setPhone] = useState(user?.phone ?? '');
  const [dateOfBirth, setDateOfBirth] = useState(user?.profile?.date_of_birth ?? '');
  const [nationalId, setNationalId] = useState(user?.profile?.national_id ?? '');
  const [bio, setBio] = useState(user?.profile?.bio ?? '');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: me } = useQuery({
    queryKey: ['me', user?.id],
    queryFn: authApi.getMe,
    enabled: Boolean(user?.id && accessToken),
    staleTime: 0,
  });

  useEffect(() => {
    if (me && user?.id && me.id === user.id) {
      setUser(me);
      setFirstName(me.first_name);
      setLastName(me.last_name);
      setPhone(me.phone);
      setDateOfBirth(me.profile?.date_of_birth ?? '');
      setNationalId(me.profile?.national_id ?? '');
      setBio(me.profile?.bio ?? '');
    }
  }, [me, user?.id, setUser]);

  const updateMutation = useMutation({
    mutationFn: () =>
      authApi.updateMe({
        first_name: firstName,
        last_name: lastName,
        phone,
        date_of_birth: dateOfBirth || null,
        national_id: nationalId,
        bio,
      }),
    onSuccess: (updated) => {
      setUser(updated);
      setFeedback({ type: 'success', text: 'Profile updated successfully.' });
    },
    onError: (err) => {
      setFeedback({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    updateMutation.mutate();
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 700 }}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}
      >
        <Box>
          <Typography variant="h4">My Profile</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              {user?.username} &middot; {user?.email}
            </Typography>
            {user && <StatusChip value={user.role} />}
          </Stack>
        </Box>
        <Button variant="outlined" onClick={() => navigate('/profile/address')}>
          Manage Addresses
        </Button>
      </Stack>

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Box component="form" onSubmit={handleSubmit}>
            <Stack spacing={2.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="First Name"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  fullWidth
                />
                <TextField
                  label="Last Name"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  fullWidth
                />
              </Stack>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  fullWidth
                />
                <TextField
                  label="Date of Birth"
                  type="date"
                  slotProps={{ inputLabel: { shrink: true } }}
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  fullWidth
                />
              </Stack>

              <TextField
                label="National ID / Passport"
                value={nationalId}
                onChange={(e) => setNationalId(e.target.value)}
                fullWidth
              />

              <TextField
                label="Bio / Notes"
                multiline
                rows={3}
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                fullWidth
              />

              <Box>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
              </Box>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}

