import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { formatPeruDate } from '../peru-date-time';
import { ExcludedDateRange } from '../reservation-rules.model';

@Component({
  selector: 'app-reservation-rules-editor',
  imports: [FormsModule],
  templateUrl: './reservation-rules-editor.component.html',
  styleUrl: './reservation-rules-editor.component.css',
})
export class ReservationRulesEditorComponent {
  @Input({ required: true }) controlPrefix = 'reservationRules';
  @Input() disabled = false;
  @Input() showMinimumHour = true;
  @Input() minimumDate = '';
  @Input() maximumDate = '';
  @Input() minimumHour = '';
  @Input() allowedWeekdays: number[] = [];
  @Input() excludedDateRanges: readonly ExcludedDateRange[] = [];
  @Input() excludedDateStart = '';
  @Input() excludedDateEnd = '';

  @Output() readonly minimumDateChange = new EventEmitter<string>();
  @Output() readonly maximumDateChange = new EventEmitter<string>();
  @Output() readonly minimumHourChange = new EventEmitter<string>();
  @Output() readonly allowedWeekdaysChange = new EventEmitter<number[]>();
  @Output() readonly excludedDateStartChange = new EventEmitter<string>();
  @Output() readonly excludedDateEndChange = new EventEmitter<string>();
  @Output() readonly addExcludedDateRange = new EventEmitter<void>();
  @Output() readonly removeExcludedDateRange = new EventEmitter<number>();

  protected readonly formatDate = formatPeruDate;
}
