import { IsNotEmpty, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class GetLicenseDto {
  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
    description: 'Users license number',
  })
  license_number: string;
}
