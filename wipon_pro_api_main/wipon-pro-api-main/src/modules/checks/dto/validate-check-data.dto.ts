import { IsBase64, IsIn, IsNotEmpty, IsOptional, IsString } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class ValidateCheckDataDto {
  @IsNotEmpty()
  @IsIn(['serial_number', 'excise_code', 'bf_serial_number', 'bf_excise_code'])
  @ApiProperty({
    type: String,
    description: 'Type must be one of this values: [serial_number, excise_code, bf_serial_number, bf_excise_code]',
    required: true,
  })
  type: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    description: 'Code for checking the item',
    required: true,
  })
  code: string;

  @IsOptional()
  @ApiProperty({
    type: Number,
    required: false,
  })
  latitude: number;

  @IsOptional()
  @ApiProperty({
    type: Number,
    required: false,
  })
  longitude: number;

  @IsOptional()
  @ApiProperty({
    type: Number,
    required: false,
  })
  accuracy: number;

  @IsOptional()
  @ApiProperty({
    type: String,
    required: false,
  })
  third_party: string;

  @IsOptional()
  @ApiProperty({
    type: String,
    required: false,
  })
  hash: string;

  @IsOptional()
  @ApiProperty({
    type: String,
    required: false,
  })
  gtin: string;

  @IsOptional()
  @IsBase64()
  @ApiProperty({
    type: String,
    description: 'Picture of item in Base64 format',
    required: false,
  })
  sticker_photo: string;
}
