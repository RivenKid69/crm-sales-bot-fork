import { IsEmail, IsNotEmpty, IsOptional, IsString, Matches } from 'class-validator';
import { IsDgdExists, IsStoreTypeExists, IsUgdExists } from '../../../common/validations/is-entity-exists';
import { IsNumeric } from '../../../common/validations/is-numeric';
import { ApiProperty } from '@nestjs/swagger';

export class NewFormOfSavingStoreDto {
  @IsNotEmpty()
  @IsNumeric()
  @IsStoreTypeExists({
    message: 'Store type with ID $value does not exists',
  })
  @ApiProperty({
    type: Number,
    required: true,
  })
  buisness_store_type_id: number;

  @IsNotEmpty()
  @Matches(/^\d{12}$/, {
    message: 'Payer bin must be only digits and 12 length',
  })
  @ApiProperty({
    type: String,
    required: true,
    description: 'Payer bin must be only digits and 12 length',
  })
  payer_bin: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  payer_name: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  payer_address: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  payer_postal_address: string;

  @IsNotEmpty()
  @Matches(/^\d{12}$/, {
    message: 'Payer bin must be only digits and 12 length',
  })
  @ApiProperty({
    type: String,
    required: true,
    description: 'Buisness bin must be only digits and 12 length',
  })
  buisness_bin: string;

  @IsNotEmpty()
  @IsNumeric({
    message: 'license_number must be numeric',
  })
  @ApiProperty({
    type: String,
    required: true,
  })
  // Regexp: ^(\d|-|\/)*$ или ^(\d|\-|\/)*$ - Выяснить правильный вариант
  license_number: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  buisness_store_address: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  buisness_full_legal_name: string;

  @IsNotEmpty()
  @IsString()
  @ApiProperty({
    type: String,
    required: true,
  })
  buisness_store_name: string;

  @IsNotEmpty()
  @IsDgdExists({
    message: 'Dgd with ID $value does not exists',
  })
  @ApiProperty({
    type: String,
    required: true,
  })
  buisness_dgd_id: string;

  @IsOptional()
  @IsUgdExists({
    message: 'Ugd with ID $value does not exists',
  })
  @ApiProperty({
    type: String,
    required: false,
  })
  buisness_ugd_id: string;

  @IsOptional()
  @IsEmail()
  @ApiProperty({
    type: String,
    required: false,
  })
  payer_email: string;
}
