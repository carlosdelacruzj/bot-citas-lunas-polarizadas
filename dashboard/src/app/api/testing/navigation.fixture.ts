import type {
  CaptchaAuthorityControl,
  CaptchaEventsPage,
  CaptchaQuality,
  CaptchaQualityCasesPage,
  CaptchaSamplingControl,
  CaptchaSummary,
} from '../captchas/captchas.contracts';
import type {
  FinanceCategory,
  FinanceDataQualitySummary,
  FinanceEntry,
  FinanceMonthClosure,
  FinanceSummary,
  MonthlySummaryV2,
} from '../finance/finance.contracts';
import type {
  AppointmentReminderStatus,
  PostAppointmentPayload,
} from '../followups/followups.contracts';
import type { WhatsAppMessageTemplatesResponse } from '../messages/messages.contracts';
import type {
  OperatorInboxPayload,
  OpportunityBurstsResponse,
  OpportunityControl,
} from '../operations/operations.contracts';

interface NavigationResponses {
  '/api/v1/appointment-reminders': AppointmentReminderStatus;
  '/api/v1/operator-inbox': OperatorInboxPayload;
  '/api/v1/post-appointment-followups': PostAppointmentPayload;
  '/api/v1/runtime-controls/opportunity': OpportunityControl;
  '/api/v1/opportunity-bursts': OpportunityBurstsResponse;
  '/api/v1/runtime-controls/captcha-sampling': CaptchaSamplingControl;
  '/api/v1/runtime-controls/captcha-authority': CaptchaAuthorityControl;
  '/api/v1/captcha-shadow/summary': CaptchaSummary;
  '/api/v1/captcha-shadow/events': CaptchaEventsPage;
  '/api/v1/captcha-shadow/quality': CaptchaQuality;
  '/api/v1/captcha-shadow/quality/cases': CaptchaQualityCasesPage;
  '/api/v2/monthly-summary': MonthlySummaryV2;
  '/api/v1/finance/summary': FinanceSummary;
  '/api/v1/finance/data-quality': FinanceDataQualitySummary;
  '/api/v1/finance/month-closure': FinanceMonthClosure;
  '/api/v1/finance/categories': { categories: FinanceCategory[] };
  '/api/v1/finance/entries': { entries: FinanceEntry[] };
  '/api/v1/whatsapp-message-templates': WhatsAppMessageTemplatesResponse;
}

const navigationResponses = {
  "/api/v1/appointment-reminders": {
    "service_date": "2026-09-08",
    "appointment_day": "",
    "current_time": "",
    "scheduler_window_open": false,
    "configuration": {
      "enabled": false,
      "dry_run": false,
      "time": "",
      "summary_grace_minutes": 0,
      "reconcile_seconds": 0,
      "send_interval_seconds": 0,
      "daily_limit": 0,
      "timezone": "",
      "effective_lead_days": 1
    },
    "control": {
      "mode": "disabled",
      "lead_days": 1,
      "message_template": "",
      "default_template": "",
      "revision": 0,
      "template_revision": 0,
      "updated_at": "2026-09-08T10:00:00-05:00",
      "updated_by": "",
      "applies_from": "",
      "lead_days_applies_from": "current_service_date",
      "existing_jobs_policy": "preserved"
    },
    "allowed_variables": [],
    "day": null,
    "job_counts": {},
    "candidates": [],
    "jobs": []
  },
  "/api/v1/operator-inbox": {
    "generated_at": "2026-09-08T10:00:00-05:00",
    "summary": {
      "total": 0,
      "access": 0,
      "paused": 0,
      "contact": 0,
      "whatsapp": 0,
      "payment": 0,
      "postpayment": 0,
      "messages": 0
    },
    "items": []
  },
  "/api/v1/post-appointment-followups": {
    "summary": {
      "total_confirmed": 0,
      "active_followups": 0,
      "needs_attention": 0,
      "access_lost": 0,
      "progressed_or_completed": 0
    },
    "filter_counts": {
      "active": 0,
      "attention": 0,
      "observations": 0,
      "progressed": 0,
      "history": 0,
      "access_lost": 0,
      "completed": 0
    },
    "automation": {
      "enabled": false,
      "timezone": "",
      "time": "",
      "daily_limit": 0,
      "due_count": 0,
      "running": 0,
      "completed_today": 0,
      "failed_today": 0,
      "last_run_at": null,
      "breaker_open": false,
      "breaker_reason": null
    },
    "pagination": {
      "limit": 12,
      "offset": 0,
      "total": 0
    },
    "items": []
  },
  "/api/v1/runtime-controls/opportunity": {
    "revision": 0,
    "source": "",
    "obs006": {
      "desired_mode": "",
      "effective_mode": "",
      "admissions_allowed": false
    },
    "obs007": {
      "desired_mode": "",
      "effective_mode": "",
      "admissions_allowed": false
    },
    "breaker": {
      "state": "",
      "reason": null,
      "opened_at": null
    },
    "active_burst": null,
    "updated_at": null,
    "updated_by": null,
    "pending_application": false
  },
  "/api/v1/opportunity-bursts": {
    "bursts": []
  },
  "/api/v1/runtime-controls/captcha-sampling": {
    "enabled": false,
    "sample_limit": 0,
    "effective_sample_limit": 0,
    "estimated_extra_seconds": 0,
    "applies_from": "next_captcha_batch",
    "rapid_mode_effective_sample_limit": 1,
    "updated_at": null,
    "updated_by": "",
    "source": "database"
  },
  "/api/v1/runtime-controls/captcha-authority": {
    "mode": "2captcha",
    "canary_limit": 0,
    "local_decisions": 0,
    "local_confirmed": 0,
    "local_rejected": 0,
    "fallback_decisions": 0,
    "remaining_local_decisions": 0,
    "local_admission_open": false,
    "min_char_confidence": 0,
    "sequence_confidence_product": 0,
    "timeout_ms": 0,
    "circuit_state": "closed",
    "circuit_reason": null,
    "circuit_opened_at": null,
    "activated_at": null,
    "updated_at": "2026-09-08T10:00:00-05:00",
    "updated_by": "",
    "applies_from": "next_reservation_captcha",
    "rollback": {
      "mode": "2captcha"
    }
  },
  "/api/v1/captcha-shadow/summary": {
    "status": "",
    "device": null,
    "models": [],
    "selected_model": "",
    "started_at_utc": null,
    "stats": {
      "events": 0,
      "with_external_answer": 0,
      "portal_accepted": 0,
      "human_labeled": 0,
      "models": {}
    },
    "outbox": {
      "pending": 0,
      "processed": 0,
      "attempts": 0
    }
  },
  "/api/v1/captcha-shadow/events": {
    "events": [],
    "pagination": {
      "page": 1,
      "page_size": 12,
      "total": 0,
      "total_pages": 1
    },
    "filters": {
      "q": "",
      "agreement": "",
      "portal_status": "",
      "source": "",
      "review_status": "",
      "review_scope": "",
      "sort": ""
    }
  },
  "/api/v1/captcha-shadow/quality": {
    "events": 0,
    "validated_images": 0,
    "weeks_observed": 0,
    "trend_ready": false,
    "models": [],
    "ensemble": {
      "unanimous": 0,
      "unanimous_validated": 0,
      "unanimous_wrong": 0,
      "majority": 0,
      "majority_wrong": 0,
      "all_different": 0
    },
    "weekly": [],
    "useful_case_counts": {
      "wrong": 0,
      "high_confidence_wrong": 0,
      "unanimous_wrong": 0,
      "majority_wrong": 0,
      "disagreement": 0
    },
    "local_total_ms": {
      "samples": 0,
      "average": null,
      "p50": null,
      "p90": null
    },
    "external_solver_ms": {
      "samples": 0,
      "average": null,
      "p50": null,
      "p90": null
    },
    "definitions": {
      "accuracy_reference": "",
      "percentile_method": "",
      "high_confidence_threshold": 0
    }
  },
  "/api/v1/captcha-shadow/quality/cases": {
    "cases": [],
    "pagination": {
      "page": 1,
      "page_size": 12,
      "total": 0,
      "total_pages": 1
    },
    "filters": {
      "type": "wrong"
    }
  },
  "/api/v2/monthly-summary": {
    "contract_version": "2.0",
    "month": "2026-09",
    "as_of": "",
    "period_metrics": {
      "period": {
        "start": "",
        "end_exclusive": "",
        "coverage_end_exclusive": "",
        "is_closed": false
      },
      "orders_created": 0,
      "confirmed_reservation_events": 0,
      "orders_reserved": 0,
      "payments_received": 0,
      "distinct_payments": 0,
      "orders_with_receipts": 0,
      "payments_received_semantics": "",
      "revenue_collected": 0,
      "receipt_date_quality": {
        "status": "no_receipts",
        "comparison_conclusive": false,
        "exact_since": null,
        "inferred_receipt_count": 0,
        "inferred_payment_count": 0,
        "inferred_amount": 0,
        "exact_receipt_count": 0,
        "exact_amount": 0,
        "semantics": ""
      },
      "average_ticket": {
        "value": 0,
        "numerator": 0,
        "denominator": 0
      },
      "daily_revenue": []
    },
    "cohort_metrics": {
      "cohort": {
        "created_from": "",
        "created_to_exclusive": "",
        "outcomes_observed_as_of": ""
      },
      "orders_created": 0,
      "orders_ever_reserved": 0,
      "orders_ever_paid": 0,
      "revenue_ever_collected": 0,
      "reservation_conversion_rate": {
        "value": 0,
        "numerator": 0,
        "denominator": 0
      },
      "payment_conversion_rate": {
        "value": 0,
        "numerator": 0,
        "denominator": 0
      },
      "funnel": {
        "validated": {
          "orders_created": 0,
          "orders_ever_reserved": 0,
          "orders_ever_paid": 0
        },
        "legacy_not_required": {
          "orders_created": 0,
          "orders_ever_reserved": 0,
          "orders_ever_paid": 0
        },
        "note": ""
      },
      "sources": [],
      "source_semantics": {
        "preferred": "",
        "historical_backfill": "",
        "historical_fallback": "",
        "frozen_storage_available": false
      }
    },
    "current_attention_snapshot": {
      "as_of": "",
      "active_orders": 0,
      "missing_contact_count": 0,
      "valid_contact_rule": "",
      "pending_payments": 0,
      "pending_amount": 0,
      "pending_payment_items": [],
      "aged_active_orders": [],
      "list_limit": 0
    },
    "comparisons": {
      "same_day_window": null,
      "closed_months": {
        "selected": {
          "period": {
            "start": "",
            "end_exclusive": "",
            "coverage_end_exclusive": "",
            "is_closed": false
          },
          "metrics": {
            "orders_created": 0,
            "confirmed_reservation_events": 0,
            "orders_reserved": 0,
            "payments_received": 0,
            "distinct_payments": 0,
            "orders_with_receipts": 0,
            "payments_received_semantics": "",
            "revenue_collected": 0,
            "receipt_date_quality": {
              "status": "no_receipts",
              "comparison_conclusive": false,
              "exact_since": null,
              "inferred_receipt_count": 0,
              "inferred_payment_count": 0,
              "inferred_amount": 0,
              "exact_receipt_count": 0,
              "exact_amount": 0,
              "semantics": ""
            },
            "average_ticket": {
              "value": 0,
              "numerator": 0,
              "denominator": 0
            },
            "daily_revenue": []
          }
        },
        "previous": {
          "period": {
            "start": "",
            "end_exclusive": "",
            "coverage_end_exclusive": "",
            "is_closed": false
          },
          "metrics": {
            "orders_created": 0,
            "confirmed_reservation_events": 0,
            "orders_reserved": 0,
            "payments_received": 0,
            "distinct_payments": 0,
            "orders_with_receipts": 0,
            "payments_received_semantics": "",
            "revenue_collected": 0,
            "receipt_date_quality": {
              "status": "no_receipts",
              "comparison_conclusive": false,
              "exact_since": null,
              "inferred_receipt_count": 0,
              "inferred_payment_count": 0,
              "inferred_amount": 0,
              "exact_receipt_count": 0,
              "exact_amount": 0,
              "semantics": ""
            },
            "average_ticket": {
              "value": 0,
              "numerator": 0,
              "denominator": 0
            },
            "daily_revenue": []
          }
        }
      }
    }
  },
  "/api/v1/finance/summary": {
    "month": "2026-09",
    "payments_received": 0,
    "distinct_payments": 0,
    "orders_with_receipts": 0,
    "payments_received_semantics": "",
    "daily_revenue": [],
    "revenue_collected": 0,
    "recognized_costs": 0,
    "operating_margin_before_unregistered_costs": 0,
    "net_cash_outflow": 0,
    "prepaid_topups": 0,
    "prepaid_consumption": 0,
    "unconverted_entries": 0,
    "active_entries": 0,
    "conversion_complete": false,
    "receipt_date_quality": {
      "status": "no_receipts",
      "comparison_conclusive": false,
      "exact_since": null,
      "inferred_receipt_count": 0,
      "inferred_payment_count": 0,
      "inferred_amount": 0,
      "exact_receipt_count": 0,
      "exact_amount": 0,
      "semantics": ""
    },
    "by_category": []
  },
  "/api/v1/finance/data-quality": {
    "month": "2026-09",
    "receipt_date_quality": {
      "status": "no_receipts",
      "comparison_conclusive": false,
      "exact_since": null,
      "inferred_receipt_count": 0,
      "inferred_payment_count": 0,
      "inferred_amount": 0,
      "exact_receipt_count": 0,
      "exact_amount": 0,
      "semantics": ""
    },
    "data_quality": {
      "actual": {
        "entry_count": 0,
        "amount_pen": 0,
        "unconverted_count": 0
      },
      "estimated": {
        "entry_count": 0,
        "amount_pen": 0,
        "unconverted_count": 0
      },
      "pending": {
        "entry_count": 0,
        "amount_pen": 0,
        "unconverted_count": 0
      }
    },
    "unconverted_entries": [],
    "paid_amount_mismatches": [],
    "unreconciled_paid_amount_mismatch_count": 0
  },
  "/api/v1/finance/month-closure": {
    "month": "2026-09",
    "closure": null,
    "movements": {
      "prepaid_topups": 0,
      "prepaid_consumption": 0,
      "refunds": 0,
      "prepaid_refunds": 0,
      "pending_entries": 0,
      "unconverted_entries": 0,
      "estimated_entries": 0
    },
    "expected_closing_prepaid_balance": null,
    "balance_difference": null
  },
  "/api/v1/finance/categories": {
    "categories": []
  },
  "/api/v1/finance/entries": {
    "entries": []
  },
  "/api/v1/whatsapp-message-templates": {
    "status": "ok",
    "templates": []
  }
} satisfies NavigationResponses;

export default navigationResponses;
