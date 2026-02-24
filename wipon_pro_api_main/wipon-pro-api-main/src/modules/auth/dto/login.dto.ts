import { IsIn, IsNotEmpty, IsOptional, IsPhoneNumber, Length } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
export class LoginDto {
  @IsNotEmpty()
  @IsPhoneNumber('KZ')
  @ApiProperty({
    type: String,
    description: 'Phone number (KZ)',
  })
  phone_number: string;

  @IsOptional()
  @Length(6, 6)
  @ApiProperty({
    type: String,
    description: 'Auth code that sent to your phone number (First, you should make request with only phone_number).',
    required: false,
  })
  auth_code: string;

  @IsOptional()
  @ApiProperty({
    type: String,
    description: 'Application type that uses user',
    required: false,
  })
  @IsIn(['desktop', 'mobile_scan'])
  application_type: string;
}
