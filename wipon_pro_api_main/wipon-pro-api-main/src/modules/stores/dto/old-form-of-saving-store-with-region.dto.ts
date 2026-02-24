import { IsInt, IsNotEmpty, IsOptional, IsString, Matches } from 'class-validator';
import { IsRegionExists, IsStoreTypeExists } from '../../../common/validations/is-entity-exists';
import { IsNumeric } from '../../../common/validations/is-numeric';

export class OldFormOfSavingStoreWithRegionDto {
  @IsNotEmpty()
  @IsInt()
  @IsRegionExists({
    message: 'Region with ID $value does not exists',
  })
  region_id: number;

  @IsNotEmpty()
  @IsNumeric()
  @IsStoreTypeExists({
    message: 'Store type with ID $value does not exists',
  })
  store_type_id: number;

  @IsOptional()
  @IsString()
  city: string;

  @IsOptional()
  @IsString()
  street: string;

  @IsOptional()
  @IsString()
  house: string;

  @IsOptional()
  @IsString()
  name: string;

  @IsNotEmpty()
  @Matches(/^\d{12}$/)
  bin: string;

  @IsNotEmpty()
  @IsString()
  legal_name: string;

  @IsNotEmpty()
  @IsString()
  license_number: string;

  @IsOptional()
  @IsString()
  address: string;
}
