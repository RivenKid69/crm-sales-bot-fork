import { IsEmail, IsIn, IsObject, IsOptional, IsPhoneNumber, IsString } from 'class-validator';
import { userDeviceType } from '../../../common/types/user-device.type';
import { ApiProperty } from '@nestjs/swagger';

export class UpdateUserDto {
  @IsOptional()
  @IsPhoneNumber('KZ')
  @ApiProperty({
    type: String,
    required: false,
  })
  phone_number: string;

  @IsOptional()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  name: string;

  @IsOptional()
  @IsEmail()
  @ApiProperty({
    type: String,
    required: false,
  })
  email: string;

  @IsOptional()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  work_phone_number: string;

  @IsOptional()
  @IsIn(['ru', 'kk', 'en'])
  @ApiProperty({
    type: String,
    required: false,
  })
  app_language: string;

  @IsOptional()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  app_version: string;

  @IsOptional()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  third_party: string;

  @IsOptional()
  @IsObject()
  @ApiProperty({
    type: Object,
    required: false,
  })
  device: userDeviceType;

  @IsOptional()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  push_token: string;
}
