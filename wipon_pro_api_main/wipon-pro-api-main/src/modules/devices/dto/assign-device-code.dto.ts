import { IsIn, IsNotEmpty, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class AssignDeviceCodeDto {
  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  device_code: string;

  @IsNotEmpty()
  @IsIn(['desktop', 'mobile_scan'])
  @ApiProperty({
    type: String,
    description: 'Must be one of this: [desktop, mobile_scan]',
    required: true,
  })
  application_type: string;
}
