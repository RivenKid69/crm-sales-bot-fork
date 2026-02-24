import { IsBoolean, IsNotEmpty } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class UpdateNotificationStatusDto {
  @IsNotEmpty()
  @IsBoolean()
  @ApiProperty({
    type: Boolean,
    required: true,
  })
  is_unread: boolean;
}
