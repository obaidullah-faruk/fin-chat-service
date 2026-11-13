/**
 * Utility constants and helpers for the ChatWidget.
 */

/** Maps MCP tool names to user-friendly progress messages. */
const TOOL_FRIENDLY_MESSAGES: Record<string, string> = {
  get_balance: 'Fetching your account balance...',
  get_account_info: 'Retrieving your account details...',
  get_transactions: 'Loading your transaction history...',
  get_statement: 'Generating your account statement...',
  request_cheque_book: 'Processing your cheque book request...',
  update_address: 'Updating your address...',
  get_kyc_status: 'Checking your KYC verification status...',
};

/** Maps stage strings to human-readable progress labels. */
const STAGE_LABELS: Record<string, string> = {
  pii_scan: 'Scanning for sensitive data...',
  pii_redacted: 'Privacy protection applied',
  routing: 'Analyzing your request...',
  routed: 'Connecting to banking agent...',
  init: 'Connecting to FinChat...',
  tool: 'Retrieving banking data...',
};

/**
 * Returns a user-friendly progress message for a tool call.
 * Falls back to a generic message if the tool name is unknown.
 */
export function getToolProgressMessage(toolName: string): string {
  return TOOL_FRIENDLY_MESSAGES[toolName] ?? 'Retrieving banking data...';
}

/**
 * Returns a human-readable label for a progress stage.
 */
export function getStageLabelText(stage: string): string {
  for (const [key, label] of Object.entries(STAGE_LABELS)) {
    if (stage.includes(key)) return label;
  }
  return 'Processing your request...';
}

/** Stage category for icon/color selection. */
export type StageCategory = 'pii' | 'routing' | 'tool' | 'error' | 'default';

export function getStageCategory(stage: string): StageCategory {
  if (stage === 'error') return 'error';
  if (stage.includes('pii')) return 'pii';
  if (stage.includes('rout')) return 'routing';
  if (stage.includes('tool') || stage === 'tool') return 'tool';
  return 'default';
}

