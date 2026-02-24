import { IsIn, IsNotEmpty, IsString } from 'class-validator';
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from '../../../config/subscription.config';
import { IsNumeric } from '../../../common/validations/is-numeric';

export class GenerateInvoiceDto {
  @IsNotEmpty()
  @IsIn([MOBILE_TYPE, DESKTOP_TYPE, TSD_TYPE])
  type: number;

  @IsNotEmpty()
  @IsNumeric()
  bin: number;

  @IsNotEmpty()
  @IsString()
  organization: string;

  @IsNotEmpty()
  @IsNumeric()
  account_number: number;
}
