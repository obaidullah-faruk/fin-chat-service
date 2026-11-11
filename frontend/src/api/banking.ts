import { apiClient } from './client';
import type {
  AccountLookupItem,
  BankAccount,
  CustomerDetail360,
  CustomerListItem,
  FundingSource,
  PaginatedResponse,
  StaffDashboardSummary,
  Transaction,
  WithdrawalMethod,
} from '../types';

export const bankingApi = {
  getMyAccount: async (): Promise<BankAccount> => {
    const { data } = await apiClient.get<BankAccount>('/banking/account/');
    return data;
  },

  updateAccountType: async (
    account_type: 'savings' | 'current' | 'salary'
  ): Promise<BankAccount> => {
    const { data } = await apiClient.patch<BankAccount>('/banking/account/', {
      account_type,
    });
    return data;
  },

  deposit: async (payload: {
    amount: string;
    funding_source?: FundingSource;
    description?: string;
  }): Promise<Transaction> => {
    const { data } = await apiClient.post<Transaction>('/banking/deposit/', payload);
    return data;
  },

  withdraw: async (payload: {
    amount: string;
    withdrawal_method?: WithdrawalMethod;
    description?: string;
  }): Promise<Transaction> => {
    const { data } = await apiClient.post<Transaction>('/banking/withdraw/', payload);
    return data;
  },

  transfer: async (payload: {
    to_account_number: string;
    amount: string;
    description?: string;
  }): Promise<Transaction> => {
    const { data } = await apiClient.post<Transaction>('/banking/transfer/', payload);
    return data;
  },

  lookupAccounts: async (query = ''): Promise<AccountLookupItem[]> => {
    const { data } = await apiClient.get<AccountLookupItem[]>('/banking/lookup/', {
      params: { q: query },
    });
    return data;
  },

  getTransactions: async (params?: {
    page?: number;
    transaction_type?: string;
    channel?: string;
    search?: string;
    scope?: 'all' | 'mine';
    user_id?: number;
  }): Promise<PaginatedResponse<Transaction>> => {
    const { data } = await apiClient.get<PaginatedResponse<Transaction>>(
      '/banking/transactions/',
      { params }
    );
    return data;
  },

  getStaffDashboard: async (): Promise<StaffDashboardSummary> => {
    const { data } = await apiClient.get<StaffDashboardSummary>('/banking/dashboard-summary/');
    return data;
  },

  getCustomers: async (params?: {
    page?: number;
    search?: string;
    account_type?: string;
    account_active?: string;
    is_usd_endorsed?: string;
    role?: string;
  }): Promise<PaginatedResponse<CustomerListItem>> => {
    const { data } = await apiClient.get<PaginatedResponse<CustomerListItem>>(
      '/banking/customers/',
      { params }
    );
    return data;
  },

  getCustomerDetail: async (userId: number): Promise<CustomerDetail360> => {
    const { data } = await apiClient.get<CustomerDetail360>(`/banking/customers/${userId}/`);
    return data;
  },

  updateCustomerAccount: async (
    userId: number,
    payload: {
      account_type?: 'savings' | 'current' | 'salary';
      is_active?: boolean;
      reason?: string;
    }
  ): Promise<BankAccount> => {
    const { data } = await apiClient.patch<BankAccount>(
      `/banking/customers/${userId}/account/`,
      payload
    );
    return data;
  },

  tellerDeposit: async (
    userId: number,
    payload: { amount: string; description?: string }
  ): Promise<Transaction> => {
    const { data } = await apiClient.post<Transaction>(
      `/banking/customers/${userId}/deposit/`,
      payload
    );
    return data;
  },

  tellerWithdraw: async (
    userId: number,
    payload: { amount: string; description?: string }
  ): Promise<Transaction> => {
    const { data } = await apiClient.post<Transaction>(
      `/banking/customers/${userId}/withdraw/`,
      payload
    );
    return data;
  },
};
