import { IsNotEmpty, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class CheckDeviceDto {
  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    description: 'Application type for checking users device code',
    required: true,
  })
  application_type: string;
}
