import { IsIn, IsInt, IsJSON, IsNotEmpty, IsNumber, IsNumberString, IsOptional, IsString } from 'class-validator';
import { IsLedgerExists } from '../../../common/validations/is-entity-exists';
import { IsNumeric } from '../../../common/validations/is-numeric';

export class PostTransactionDto {
  @IsNotEmpty()
  @IsInt()
  user_id: number;

  @IsNotEmpty()
  @IsString()
  @IsIn(['Wipon', 'bank', 'qiwi', 'kassa24', 'cyberplat', 'wipon_transfer'])
  provider: string;

  @IsNotEmpty()
  @IsNumeric({
    message: 'amount must be numeric',
  })
  amount: number;

  @IsOptional()
  @IsInt()
  timestamp: number;

  @IsOptional()
  @IsString()
  @IsIn(['Wipon', 'bank', 'qiwi', 'kassa24', 'cyberplat'])
  account: string;

  @IsOptional()
  @IsInt()
  @IsLedgerExists({
    message: 'Ledger with ID $value does not exists',
  })
  contracter_id: number;

  @IsOptional()
  @IsJSON()
  raw_info: string;
}
