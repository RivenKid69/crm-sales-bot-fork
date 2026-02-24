import { IsJSON, IsNotEmpty, IsOptional } from 'class-validator';
import { IsNumeric } from '../../../common/validations/is-numeric';

export class PostTransferDto {
  @IsNotEmpty()
  @IsNumeric({
    message: 'from_user_id must be numeric',
  })
  from_user_id: number;

  @IsNotEmpty()
  @IsNumeric({
    message: 'from_user_id must be numeric',
  })
  to_user_id: number;

  @IsNotEmpty()
  @IsNumeric()
  sum: number;

  @IsOptional()
  @IsJSON()
  raw_info_from: string;

  @IsOptional()
  @IsJSON()
  raw_info_to: string;
}
