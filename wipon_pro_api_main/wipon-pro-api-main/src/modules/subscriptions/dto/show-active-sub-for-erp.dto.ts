import { IsNotEmpty, IsPhoneNumber, IsString } from 'class-validator';

export class ShowActiveSubForErpDto {
  @IsNotEmpty()
  @IsPhoneNumber('KZ')
  phone_number: string;

  @IsNotEmpty()
  @IsString()
  bin: string;
}
