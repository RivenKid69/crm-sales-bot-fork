import { IsOptional, IsString } from 'class-validator';

export class UpdateStoreAndUserNameDto {
  @IsOptional()
  @IsString()
  buisness_bin: string;

  @IsString()
  buisness_full_legal_name: string;

  @IsString()
  buisness_store_name: string;

  @IsString()
  buisness_store_address: string;

  @IsOptional()
  @IsString()
  license_number: string;

  @IsString()
  name: string;

  @IsOptional()
  @IsString()
  bin: string;

  @IsOptional()
  phone: string;
}
