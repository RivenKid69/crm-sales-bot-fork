import { IsIn, IsNotEmpty } from 'class-validator';
import { IsNumeric } from '../../../common/validations/is-numeric';
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from '../../../config/subscription.config';
import { ApiProperty } from '@nestjs/swagger';

export class MakeRefundDto {
  @IsNotEmpty()
  @IsNumeric()
  @IsIn([MOBILE_TYPE, DESKTOP_TYPE, TSD_TYPE])
  @ApiProperty({
    type: Number,
    required: true,
    description: 'Type of buying subscription',
  })
  type: number;

  @IsNotEmpty()
  @IsNumeric()
  @ApiProperty({
    type: Number,
    required: true,
    description: 'ID of subscription (Can be device_id or subscription_id)',
  })
  id: number;
}
