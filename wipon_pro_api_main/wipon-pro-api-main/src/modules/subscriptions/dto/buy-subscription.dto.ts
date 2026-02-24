import { IsBoolean, IsIn, IsNotEmpty, IsOptional } from 'class-validator';
import { DESKTOP_TYPE, MOBILE_TYPE, TSD_TYPE } from '../../../config/subscription.config';
import { ApiProperty } from '@nestjs/swagger';

export class BuySubscriptionDto {
  @IsNotEmpty()
  @IsIn([MOBILE_TYPE, DESKTOP_TYPE, TSD_TYPE])
  @ApiProperty({
    type: Number,
    required: true,
    description: 'Type of buying subscription',
  })
  type: number;

  @IsOptional()
  @IsBoolean()
  @ApiProperty({
    type: Boolean,
    required: false,
    description: 'Change users subscription type before buying subscription',
  })
  change_subscription_type: boolean;
}
