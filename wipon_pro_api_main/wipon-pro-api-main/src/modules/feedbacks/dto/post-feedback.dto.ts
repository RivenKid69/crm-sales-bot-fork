import { IsBase64, IsEmail, IsJSON, IsNotEmpty, IsOptional, IsPhoneNumber, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class PostFeedbackDto {
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

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: false,
  })
  text: string;

  @IsOptional()
  @IsJSON()
  @ApiProperty({
    type: String,
    required: false,
    description: 'Must be JSON type',
  })
  app_log: string;

  @IsOptional()
  @IsBase64()
  @ApiProperty({
    type: String,
    required: false,
    description: 'Must be Base64 image type',
  })
  photo: string;
}
