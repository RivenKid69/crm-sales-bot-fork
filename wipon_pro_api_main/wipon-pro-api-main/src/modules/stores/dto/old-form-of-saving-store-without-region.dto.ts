import { IsInt, IsNotEmpty, IsOptional, IsString, Matches } from 'class-validator';
import { IsDgdExists, IsStoreTypeExists, IsUgdExists } from '../../../common/validations/is-entity-exists';
import { IsNumeric } from '../../../common/validations/is-numeric';

export class OldFormOfSavingStoreWithoutRegionDto {
  @IsNotEmpty()
  @IsDgdExists({
    message: 'Dgd with ID $value does not exists',
  })
  buisness_dgd_id: string;

  @IsOptional()
  @IsUgdExists({
    message: 'Ugd with ID $value does not exists',
  })
  buisness_ugd_id: string;

  @IsNotEmpty()
  @IsNumeric()
  @IsStoreTypeExists({
    message: 'Store type with ID $value does not exists',
  })
  store_type_id: number;

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
