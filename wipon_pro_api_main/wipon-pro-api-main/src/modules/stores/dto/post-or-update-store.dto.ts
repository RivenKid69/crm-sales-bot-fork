import { IsOptional, IsString } from 'class-validator';

export class PostOrUpdateStoreDto {
  buisness_store_type_id: number;

  @IsOptional()
  @IsString()
  payer_bin: string;

  payer_address: string;
  payer_postal_address: string;

  @IsOptional()
  @IsString()
  buisness_bin: string;

  license_number: string;
  buisness_store_address: string;
  buisness_full_legal_name: string;
  buisness_store_name: string;
  buisness_ugd_id: string;
  buisness_dgd_id: string;
  payer_email: string;
  payer_name: string;
  region_id: number;
  store_type_id: number;
  city: string;
  street: string;
  house: string;
  name: string;

  @IsOptional()
  @IsString()
  bin: string;

  legal_name: string;
  address: string;
}
