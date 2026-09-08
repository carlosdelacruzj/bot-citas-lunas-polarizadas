import { Injectable, computed, inject, signal } from '@angular/core';
import { AppointmentApiService, type ServiceOrder } from '../../appointment-api.service';
import type { RequestScope } from '../../request-cancellation';
import { peruDateTimeSortValue } from '../../peru-date-time';
import { paginationWindow } from '../../pagination';

export type OrdersListView = Omit<
  OrdersListFacade,
  'fetchOrders' | 'replaceOrders' | 'includeOrder'
>;

type SortDirection = 'asc' | 'desc';

type OrderQuickFilter =
  | 'all'
  | 'ready'
  | 'payment_pending'
  | 'confirmed'
  | 'archived'
  | 'closed_no_charge'
  | 'restricted';

type OrderSortKey =
  | 'queue'
  | 'priority'
  | 'created_at'
  | 'updated_at'
  | 'status'
  | 'reservation'
  | 'payment'
  | 'closure'
  | 'applicant';

type OrderViewState = {
  quickFilter: OrderQuickFilter;
  sortKey: OrderSortKey;
  sortDirection: SortDirection;
  page: number;
  pageSize: number;
};

const ORDER_VIEW_STATE_KEY = 'appointment-dashboard-order-view';

const ORDER_SEARCH_SESSION_KEY = 'appointment-dashboard-order-search';

const ORDER_PAGE_SIZES = [10, 20, 50] as const;

const ORDER_QUICK_FILTERS: readonly OrderQuickFilter[] = [
  'all',
  'ready',
  'payment_pending',
  'confirmed',
  'archived',
  'closed_no_charge',
  'restricted',
];

const ORDER_SORT_KEYS: readonly OrderSortKey[] = [
  'queue',
  'priority',
  'created_at',
  'updated_at',
  'status',
  'reservation',
  'payment',
  'closure',
  'applicant',
];

const DEFAULT_ORDER_VIEW_STATE: OrderViewState = {
  quickFilter: 'all',
  sortKey: 'queue',
  sortDirection: 'desc',
  page: 1,
  pageSize: 20,
};
function readOrderViewState(): OrderViewState {
  try {
    const stored = JSON.parse(
      window.localStorage.getItem(ORDER_VIEW_STATE_KEY) ?? '{}',
    ) as Partial<OrderViewState>;
    return {
      quickFilter: ORDER_QUICK_FILTERS.includes(stored.quickFilter as OrderQuickFilter)
        ? (stored.quickFilter as OrderQuickFilter)
        : DEFAULT_ORDER_VIEW_STATE.quickFilter,
      sortKey: ORDER_SORT_KEYS.includes(stored.sortKey as OrderSortKey)
        ? (stored.sortKey as OrderSortKey)
        : DEFAULT_ORDER_VIEW_STATE.sortKey,
      sortDirection: stored.sortDirection === 'asc' ? 'asc' : 'desc',
      page: Number.isInteger(stored.page) && Number(stored.page) > 0 ? Number(stored.page) : 1,
      pageSize: ORDER_PAGE_SIZES.includes(stored.pageSize as (typeof ORDER_PAGE_SIZES)[number])
        ? Number(stored.pageSize)
        : DEFAULT_ORDER_VIEW_STATE.pageSize,
    };
  } catch {
    return DEFAULT_ORDER_VIEW_STATE;
  }
}

function readOrderSearch(): string {
  try {
    return window.sessionStorage.getItem(ORDER_SEARCH_SESSION_KEY) ?? '';
  } catch {
    return '';
  }
}

function compareOptionalTimestamps(
  left: number | null,
  right: number | null,
  direction: number,
): number {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  return (left - right) * direction;
}

@Injectable()
export class OrdersListFacade {
  private readonly api = inject(AppointmentApiService);
  private readonly initialViewState = readOrderViewState();
  private readonly orderFilterState = signal(readOrderSearch());
  public readonly orderFilter = this.orderFilterState.asReadonly();

  private readonly orderQuickFilterState = signal<OrderQuickFilter>(
    this.initialViewState.quickFilter,
  );
  public readonly orderQuickFilter = this.orderQuickFilterState.asReadonly();

  private readonly orderSortKeyState = signal<OrderSortKey>(this.initialViewState.sortKey);
  public readonly orderSortKey = this.orderSortKeyState.asReadonly();

  private readonly orderSortDirectionState = signal<SortDirection>(
    this.initialViewState.sortDirection,
  );
  public readonly orderSortDirection = this.orderSortDirectionState.asReadonly();

  private readonly orderPageState = signal(this.initialViewState.page);
  public readonly orderPage = this.orderPageState.asReadonly();

  private readonly orderPageSizeState = signal(this.initialViewState.pageSize);
  public readonly orderPageSize = this.orderPageSizeState.asReadonly();

  private readonly ordersState = signal<ServiceOrder[]>([]);
  public readonly orders = this.ordersState.asReadonly();

  public readonly filteredOrders = computed(() => {
    const filter = this.orderFilter().trim().toLowerCase();
    const quickFilter = this.orderQuickFilter();
    const filtered = this.orders().filter((order) => {
      const matchesText =
        !filter ||
        [
          order.order_id,
          order.applicant_name,
          order.document_number_masked,
          order.contact_name,
          order.contact_source,
          order.contact_whatsapp_masked,
          order.status,
          order.reservation_status,
          order.payment_status,
          order.closure_reason,
          order.closure_note,
          order.program_expediente,
          order.program_plate,
          order.parent_order_id,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(filter));
      return matchesText && this.matchesOrderQuickFilter(order, quickFilter);
    });
    return this.sortOrders(filtered);
  });

  public readonly orderTotalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredOrders().length / this.orderPageSize())),
  );

  public readonly currentOrderPage = computed(() =>
    Math.min(this.orderPage(), this.orderTotalPages()),
  );

  public readonly paginatedOrders = computed(() => {
    const start = (this.currentOrderPage() - 1) * this.orderPageSize();
    return this.filteredOrders().slice(start, start + this.orderPageSize());
  });

  public readonly orderPageStart = computed(() =>
    this.filteredOrders().length ? (this.currentOrderPage() - 1) * this.orderPageSize() + 1 : 0,
  );

  public readonly orderPageEnd = computed(() =>
    Math.min(this.currentOrderPage() * this.orderPageSize(), this.filteredOrders().length),
  );

  public readonly orderPageNumbers = computed(() =>
    paginationWindow(this.currentOrderPage(), this.orderTotalPages()),
  );

  public readonly orderQuickFilters = computed(() => [
    { key: 'all' as const, label: 'Todas', count: this.orders().length },
    { key: 'ready' as const, label: 'Listas', count: this.countOrders('ready') },
    {
      key: 'payment_pending' as const,
      label: 'Pagos pendientes',
      count: this.countOrders('payment_pending'),
    },
    { key: 'confirmed' as const, label: 'Confirmadas', count: this.countOrders('confirmed') },
    { key: 'archived' as const, label: 'Archivadas', count: this.countOrders('archived') },
    {
      key: 'closed_no_charge' as const,
      label: 'Cerradas sin cobro',
      count: this.countOrders('closed_no_charge'),
    },
    {
      key: 'restricted' as const,
      label: 'Con reglas de fecha',
      count: this.countOrders('restricted'),
    },
  ]);

  public readonly readyOrders = computed(
    () => this.orders().filter((order) => order.status === 'ready').length,
  );

  public readonly pendingPaymentOrders = computed(
    () => this.orders().filter((order) => order.payment_status === 'pending').length,
  );

  public readonly confirmedOrders = computed(
    () => this.orders().filter((order) => order.reservation_status === 'confirmed').length,
  );

  public hasReservationRestrictions(order: ServiceOrder): boolean {
    return Boolean(
      order.minimum_reservation_date ||
      order.maximum_reservation_date ||
      (order.allowed_weekdays && order.allowed_weekdays.length > 0) ||
      (order.excluded_date_ranges?.length ?? 0) > 0,
    );
  }

  public setOrderQuickFilter(filter: OrderQuickFilter): void {
    this.orderQuickFilterState.set(filter);
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public setOrderFilter(value: string): void {
    this.orderFilterState.set(value);
    this.resetOrderPage();
    this.persistOrderViewState();
    try {
      window.sessionStorage.setItem(ORDER_SEARCH_SESSION_KEY, value);
    } catch {
      // La búsqueda permanece disponible en memoria si el navegador bloquea storage.
    }
  }

  public setOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      this.orderSortDirectionState.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    } else {
      this.orderSortKeyState.set(key);
      this.orderSortDirectionState.set(this.defaultOrderSortDirection(key));
    }
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public chooseOrderSort(key: OrderSortKey): void {
    if (this.orderSortKey() === key) {
      return;
    }
    this.orderSortKeyState.set(key);
    this.orderSortDirectionState.set(this.defaultOrderSortDirection(key));
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public toggleOrderSortDirection(): void {
    this.orderSortDirectionState.set(this.orderSortDirection() === 'asc' ? 'desc' : 'asc');
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public changeOrderPageSize(value: number | string): void {
    const pageSize = Number(value);
    if (!ORDER_PAGE_SIZES.includes(pageSize as (typeof ORDER_PAGE_SIZES)[number])) {
      return;
    }
    this.orderPageSizeState.set(pageSize);
    this.resetOrderPage();
    this.persistOrderViewState();
  }

  public goToOrderPage(page: number): void {
    if (page < 1 || page > this.orderTotalPages() || page === this.currentOrderPage()) {
      return;
    }
    this.orderPageState.set(page);
    this.persistOrderViewState();
    window.requestAnimationFrame(() => {
      document.querySelector('.order-controls')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  public sortIndicator(key: OrderSortKey): string {
    if (this.orderSortKey() !== key) {
      return '';
    }
    return this.orderSortDirection() === 'asc' ? 'ASC' : 'DESC';
  }

  public orderAriaSort(key: OrderSortKey): 'ascending' | 'descending' | null {
    if (this.orderSortKey() !== key) {
      return null;
    }
    return this.orderSortDirection() === 'asc' ? 'ascending' : 'descending';
  }

  private countOrders(filter: OrderQuickFilter): number {
    return this.orders().filter((order) => this.matchesOrderQuickFilter(order, filter)).length;
  }

  private matchesOrderQuickFilter(order: ServiceOrder, filter: OrderQuickFilter): boolean {
    if (filter === 'all') {
      return true;
    }
    if (filter === 'ready') {
      return order.status === 'ready';
    }
    if (filter === 'payment_pending') {
      return order.payment_status === 'pending';
    }
    if (filter === 'confirmed') {
      return order.reservation_status === 'confirmed';
    }
    if (filter === 'archived') {
      return order.status === 'archived';
    }
    if (filter === 'closed_no_charge') {
      return order.status === 'archived' && !order.charge_required;
    }
    return this.hasReservationRestrictions(order);
  }

  private sortOrders(orders: ServiceOrder[]): ServiceOrder[] {
    const direction = this.orderSortDirection() === 'asc' ? 1 : -1;
    const key = this.orderSortKey();
    return [...orders].sort((left, right) => {
      if (key === 'queue') {
        return this.compareQueueOrder(left, right) * direction;
      }
      if (key === 'reservation') {
        const compared = compareOptionalTimestamps(
          peruDateTimeSortValue(left.reservation_date, left.reservation_hour),
          peruDateTimeSortValue(right.reservation_date, right.reservation_hour),
          direction,
        );
        if (compared !== 0) {
          return compared;
        }
        return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
      }
      const leftValue = this.orderSortValue(left, key);
      const rightValue = this.orderSortValue(right, key);
      const compared =
        typeof leftValue === 'number' && typeof rightValue === 'number'
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue), 'es', { numeric: true });
      if (compared !== 0) {
        return compared * direction;
      }
      return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
    });
  }

  private orderSortValue(order: ServiceOrder, key: OrderSortKey): string | number {
    if (key === 'queue') {
      return order.priority;
    }
    if (key === 'priority') {
      return order.priority;
    }
    if (key === 'created_at') {
      return peruDateTimeSortValue(order.created_at) ?? 0;
    }
    if (key === 'updated_at') {
      return peruDateTimeSortValue(order.updated_at) ?? 0;
    }
    if (key === 'status') {
      return order.status;
    }
    if (key === 'payment') {
      return order.payment_status ?? '';
    }
    if (key === 'closure') {
      return order.closure_reason ?? '';
    }
    return order.applicant_name ?? order.document_number_masked ?? '';
  }

  private compareQueueOrder(left: ServiceOrder, right: ServiceOrder): number {
    const priorityCompare = right.priority - left.priority;
    if (priorityCompare !== 0) {
      return priorityCompare;
    }
    const createdCompare =
      (peruDateTimeSortValue(left.created_at) ?? 0) -
      (peruDateTimeSortValue(right.created_at) ?? 0);
    if (createdCompare !== 0) {
      return createdCompare;
    }
    return left.order_id.localeCompare(right.order_id, 'es', { numeric: true });
  }

  private defaultOrderSortDirection(key: OrderSortKey): SortDirection {
    return key === 'applicant' || key === 'status' || key === 'queue' ? 'asc' : 'desc';
  }

  private resetOrderPage(): void {
    this.orderPageState.set(1);
  }

  private keepValidOrderPage(): void {
    const validPage = Math.min(this.orderPage(), this.orderTotalPages());
    if (validPage === this.orderPage()) {
      return;
    }
    this.orderPageState.set(validPage);
    this.persistOrderViewState();
  }

  private persistOrderViewState(): void {
    const state: OrderViewState = {
      quickFilter: this.orderQuickFilter(),
      sortKey: this.orderSortKey(),
      sortDirection: this.orderSortDirection(),
      page: this.orderPage(),
      pageSize: this.orderPageSize(),
    };
    try {
      window.localStorage.setItem(ORDER_VIEW_STATE_KEY, JSON.stringify(state));
    } catch {
      // El estado sigue funcionando durante la sesión si el navegador bloquea storage.
    }
  }

  public replaceOrders(orders: ServiceOrder[]): void {
    this.ordersState.set(orders);
    this.keepValidOrderPage();
  }

  public fetchOrders(scope: RequestScope): Promise<ServiceOrder[]> {
    return this.api.getServiceOrders(scope);
  }

  public includeOrder(order: ServiceOrder): void {
    this.ordersState.update((orders) => [order, ...orders.filter((item) => item.order_id !== order.order_id)]);
  }
}
