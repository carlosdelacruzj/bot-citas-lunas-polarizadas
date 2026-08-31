export type ServicePackageKey = 'standard' | 'restricted' | 'integral' | 'custom';

export interface ServicePackageDefinition {
  key: ServicePackageKey;
  label: string;
  total_amount: string | null;
  initial_payment_amount: string;
  official_fee_amount: string;
  balance_amount: string | null;
  management_fee_amount: string | null;
  fixed_price: boolean;
  default_service_type: 'standard' | 'selected_weekday' | 'custom';
  compatible_service_types: Array<'standard' | 'selected_weekday' | 'custom'>;
  requires_restrictions: boolean;
}

export interface ServicePackageCatalog {
  default_package: ServicePackageKey;
  service_packages: ServicePackageDefinition[];
}
