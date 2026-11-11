export type RoleName = 'superadmin' | 'admin' | 'manager' | 'customer';
export type WorkspaceMode = 'staff' | 'personal';

export interface Role {
  id: number;
  name: RoleName;
  description: string;
}

export interface UserProfile {
  date_of_birth: string | null;
  national_id: string;
  bio: string;
  updated_at: string;
}

export interface BankAccountSummary {
  id: number;
  account_number: string;
  account_type: 'savings' | 'current' | 'salary';
  balance: string;
  currency: string;
  is_usd_endorsed: boolean;
  usd_endorsement_limit: string;
  is_active: boolean;
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  role: RoleName;
  is_active: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  profile: UserProfile | null;
  bank_account: BankAccountSummary | null;
}

export interface Address {
  id: number;
  user: number;
  label: 'home' | 'work' | 'other';
  street: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface BankAccount {
  id: number;
  account_number: string;
  account_type: 'savings' | 'current' | 'salary';
  balance: string;
  currency: string;
  is_usd_endorsed: boolean;
  usd_endorsement_limit: string;
  is_active: boolean;
  username: string;
  owner_name: string;
  created_at: string;
  updated_at: string;
}

export interface AccountLookupItem {
  account_number: string;
  account_type: string;
  username: string;
  owner_name: string;
}

export type TransactionType = 'deposit' | 'withdrawal' | 'transfer_in' | 'transfer_out';
export type TransactionChannel = 'online' | 'atm' | 'branch_teller' | 'system';
export type FundingSource = 'bank_transfer' | 'debit_card' | 'atm_cash' | 'mobile_wallet';
export type WithdrawalMethod = 'atm_cash' | 'bank_transfer' | 'debit_card';

export interface Transaction {
  id: number;
  reference: string;
  user_id: number;
  account_number: string;
  username: string;
  owner_name: string;
  related_account_number: string | null;
  related_username: string | null;
  performed_by: number | null;
  performed_by_username: string | null;
  transaction_type: TransactionType;
  channel: TransactionChannel;
  amount: string;
  balance_after: string;
  description: string;
  created_at: string;
}

export type ActivityCategory =
  | 'auth'
  | 'banking'
  | 'cheque'
  | 'endorsement'
  | 'profile'
  | 'admin';

export interface ActivityLog {
  id: number;
  actor: number | null;
  actor_username: string | null;
  actor_role: RoleName | null;
  subject_user: number;
  subject_username: string;
  subject_full_name: string;
  category: ActivityCategory;
  action: string;
  description: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface CustomerListItem {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  role: RoleName;
  is_active: boolean;
  created_at: string;
  bank_account: BankAccount | null;
  transaction_count: number;
  pending_cheques: number;
  pending_endorsements: number;
  addresses_count: number;
}

export interface CustomerStats {
  total_deposits: string;
  total_withdrawals: string;
  total_transfers_in: string;
  total_transfers_out: string;
  transaction_count: number;
  pending_cheques: number;
  pending_endorsements: number;
  activity_count: number;
  last_transaction_at: string | null;
  last_activity_at: string | null;
}

export interface CustomerDetail360 {
  user: User;
  bank_account: BankAccount | null;
  addresses: Address[];
  stats: CustomerStats;
}

export interface StaffDashboardSummary {
  total_customers: number;
  total_bank_accounts: number;
  active_accounts: number;
  frozen_accounts: number;
  usd_endorsed_accounts: number;
  total_liquidity: string;
  total_transactions: number;
  pending_cheques: number;
  pending_endorsements: number;
  recent_transactions: Transaction[];
  recent_activities: ActivityLog[];
}

export type ChequeStatus = 'pending' | 'approved' | 'rejected' | 'issued';

export interface ChequeBookRequest {
  id: number;
  user: number;
  username: string;
  account_number: string | null;
  leaves_requested: number;
  delivery_address: number | null;
  delivery_address_snapshot: string;
  status: ChequeStatus;
  reviewed_by: number | null;
  reviewed_by_username: string | null;
  remarks: string;
  requested_at: string;
  reviewed_at: string | null;
}

export type EndorsementType = 'usd_enable' | 'usd_limit' | 'travel_quota';
export type EndorsementStatus = 'pending' | 'approved' | 'rejected';

export interface Endorsement {
  id: number;
  requester: number;
  requester_username: string;
  account_number: string | null;
  endorser: number | null;
  endorser_username: string | null;
  endorsement_type: EndorsementType;
  currency: string;
  amount: string | null;
  passport_number: string;
  status: EndorsementStatus;
  notes: string;
  review_remarks: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface ChatSession {
  id: number;
  title: string;
  message_count: number;
  last_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  session: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

