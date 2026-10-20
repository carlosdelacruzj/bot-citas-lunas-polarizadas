from __future__ import annotations

from psycopg import Connection


def _create_payment_receipt_triggers(connection: Connection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE FUNCTION validate_payment_receipt_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            original_amount numeric(12, 2);
            corrected_amount numeric(12, 2);
            original_source text;
        BEGIN
            IF NEW.source <> 'payment_correction' THEN
                RETURN NEW;
            END IF;

            SELECT amount, source
            INTO original_amount, original_source
            FROM payment_receipts
            WHERE receipt_id = NEW.corrects_receipt_id
              AND payment_id = NEW.payment_id
              AND order_id = NEW.order_id;

            IF NOT FOUND OR original_source = 'payment_correction' THEN
                RAISE EXCEPTION
                    'payment correction must reference an original receipt from the same payment';
            END IF;

            SELECT COALESCE(SUM(amount), 0)
            INTO corrected_amount
            FROM payment_receipts
            WHERE corrects_receipt_id = NEW.corrects_receipt_id
              AND payment_id = NEW.payment_id
              AND order_id = NEW.order_id;

            IF original_amount + corrected_amount + NEW.amount < 0 THEN
                RAISE EXCEPTION 'payment correction exceeds the original receipt amount';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE FUNCTION reject_payment_receipt_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'payment_receipts are immutable; insert an explicit correction movement';
        END;
        $$
        """
    )
    connection.execute(
        """
        DROP TRIGGER IF EXISTS trg_payment_receipts_validate_insert ON payment_receipts;
        CREATE TRIGGER trg_payment_receipts_validate_insert
        BEFORE INSERT ON payment_receipts
        FOR EACH ROW EXECUTE FUNCTION validate_payment_receipt_insert()
        """
    )
    connection.execute(
        """
        DROP TRIGGER IF EXISTS trg_payment_receipts_immutable ON payment_receipts;
        CREATE TRIGGER trg_payment_receipts_immutable
        BEFORE UPDATE OR DELETE ON payment_receipts
        FOR EACH ROW EXECUTE FUNCTION reject_payment_receipt_mutation()
        """
    )


def _create_finance_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_categories (
            category_code text PRIMARY KEY,
            display_name text NOT NULL,
            cost_behavior text NOT NULL CHECK (cost_behavior IN ('variable', 'fixed', 'mixed')),
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO finance_categories (category_code, display_name, cost_behavior)
        VALUES
            ('captcha', 'CAPTCHA', 'variable'),
            ('marketing', 'Marketing y publicidad', 'variable'),
            ('payment_fee', 'Comisiones de cobro', 'variable'),
            ('government_fee', 'Tasas oficiales por cuenta del cliente', 'variable'),
            ('refund', 'Devoluciones', 'variable'),
            ('internet', 'Internet', 'fixed'),
            ('electricity', 'Electricidad', 'mixed'),
            ('hosting', 'Hosting e infraestructura', 'fixed'),
            ('backup', 'Backups', 'fixed'),
            ('equipment', 'Equipos', 'fixed'),
            ('human_time', 'Tiempo humano', 'mixed'),
            ('tax', 'Impuestos', 'variable'),
            ('other', 'Otros', 'mixed')
        ON CONFLICT (category_code) DO NOTHING
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_entries (
            entry_id text PRIMARY KEY,
            occurred_on date NOT NULL,
            entry_kind text NOT NULL CHECK (
                entry_kind IN ('expense', 'prepaid_topup', 'prepaid_consumption', 'refund')
            ),
            category_code text NOT NULL REFERENCES finance_categories(category_code),
            vendor text,
            description text NOT NULL,
            amount_original numeric(12, 4) NOT NULL CHECK (amount_original > 0),
            currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
            exchange_rate_pen numeric(12, 6) CHECK (
                exchange_rate_pen IS NULL OR exchange_rate_pen > 0
            ),
            amount_pen numeric(12, 2) CHECK (amount_pen IS NULL OR amount_pen > 0),
            quantity numeric(12, 3) CHECK (quantity IS NULL OR quantity > 0),
            unit text,
            channel text,
            campaign text,
            order_id text REFERENCES service_orders(order_id) ON DELETE SET NULL,
            evidence_reference text,
            notes text,
            data_quality text NOT NULL DEFAULT 'actual' CHECK (
                data_quality IN ('actual', 'estimated', 'pending')
            ),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'voided')),
            voided_at timestamptz,
            void_reason text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            CONSTRAINT ck_finance_entries_conversion CHECK (
                (currency = 'PEN' AND exchange_rate_pen = 1 AND amount_pen IS NOT NULL)
                OR currency <> 'PEN'
            ),
            CONSTRAINT ck_finance_entries_void CHECK (
                (status = 'active' AND voided_at IS NULL AND void_reason IS NULL)
                OR (status = 'voided' AND voided_at IS NOT NULL AND void_reason IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_finance_entries_occurred
        ON finance_entries(occurred_on DESC, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_finance_entries_active_month
        ON finance_entries(occurred_on, entry_kind, category_code)
        WHERE status = 'active'
        """
    )


def _create_finance_month_closure_schema(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_month_closures (
            month_start date PRIMARY KEY CHECK (date_trunc('month', month_start) = month_start),
            opening_prepaid_balance numeric(12, 2) CHECK (
                opening_prepaid_balance IS NULL OR opening_prepaid_balance >= 0
            ),
            closing_prepaid_balance numeric(12, 2) CHECK (
                closing_prepaid_balance IS NULL OR closing_prepaid_balance >= 0
            ),
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reconciled')),
            reconciled_at timestamptz,
            reconciled_by text,
            notes text,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_finance_month_closure_reconciliation CHECK (
                (
                    status = 'draft'
                    AND reconciled_at IS NULL
                    AND reconciled_by IS NULL
                )
                OR (
                    status = 'reconciled'
                    AND opening_prepaid_balance IS NOT NULL
                    AND closing_prepaid_balance IS NOT NULL
                    AND reconciled_at IS NOT NULL
                    AND length(btrim(reconciled_by)) > 0
                )
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS payment_amount_reconciliations (
            payment_id text PRIMARY KEY REFERENCES payments(payment_id) ON DELETE CASCADE,
            resolution_type text NOT NULL CHECK (
                resolution_type IN ('discount', 'waiver', 'correction')
            ),
            reason text NOT NULL,
            reconciled_by text NOT NULL,
            reconciled_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_payment_amount_reconciliation_reason CHECK (
                length(btrim(reason)) >= 3 AND length(btrim(reconciled_by)) > 0
            )
        )
        """
    )
