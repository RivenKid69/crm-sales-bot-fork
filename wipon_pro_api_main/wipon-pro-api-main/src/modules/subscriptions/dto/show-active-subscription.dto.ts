import { IsNotEmpty, IsPhoneNumber } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ShowActiveSubscriptionDto {
  @IsNotEmpty()
  @IsPhoneNumber('KZ')
  @ApiProperty({
    type: String,
    required: true,
  })
  phone_number: string;
}
