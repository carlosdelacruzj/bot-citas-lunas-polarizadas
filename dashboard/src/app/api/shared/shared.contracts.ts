import type { ManualSessionMode } from '../states/states.contracts';

export interface ApiActionResponse {
  status: string;
  message?: string;
  command_id?: string;
  command?: string;
  released_backoff_count?: number;
  protected_backoff_count?: number;
  session_id?: string;
  mode?: ManualSessionMode;
  order_status?: string;
  order_id?: string;
  applicant_id?: string;
  portal_account_id?: string;
  contact_id?: string | null;
  parent_order_id?: string;
  parent_archived?: boolean;
  service_orders?: ApiActionResponse[];
  sent_at?: string | null;
  test_mode?: boolean;
}
